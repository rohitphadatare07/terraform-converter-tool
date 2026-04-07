"""
Agent 3 – Informed Converter

Uses the project understanding map built by ProjectUnderstandingAgent
to convert each file with full awareness of:
  - Exact variable name mappings (AWS name → GCP name)
  - Cross-module output → input wiring
  - Resource dependency chains
  - Suggested target-cloud resource types and attributes

Each file type gets a specific conversion strategy:
  - variables.tf  → regenerated using understanding.modules[x].variables mapping
  - outputs.tf    → regenerated using understanding.modules[x].outputs mapping
  - main.tf/resource files → converted block by block with per-resource attribute maps
  - root main.tf  → module call variables updated using module_wiring map
  - provider/backend → swapped provider name only
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState, ConvertedFile, FileInfo
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction
from src.mappings import get_mapping

# ── Prompts ─────────────────────────────────────────────────────────────────

RESOURCE_BLOCK_PROMPT = """Convert this {source_cloud} Terraform resource block to {target_cloud}.

RESOURCE MAPPING: {src_type} -> {tgt_type}

ATTRIBUTE MAPPING for this specific resource:
{attribute_map}

DEPENDENCY CONTEXT (other resources this block references):
{dependency_context}

SOURCE BLOCK:
{block}

Rules:
- Output ONLY the converted HCL block
- Use the attribute mapping above for field names
- Reference dependent resources using their new {target_cloud} names
- Add # comments where mapping is non-obvious

CONVERTED {target_cloud} BLOCK:"""

VARIABLES_FILE_PROMPT = """Generate a complete variables.tf for the {module_name} module
being converted from {source_cloud} to {target_cloud}.

ORIGINAL variables.tf:
{original_variables}

VARIABLE MAPPING (from project analysis):
{variable_mapping}

The converted main.tf for this module uses these variables:
{converted_main_excerpt}

Rules:
- Declare EVERY variable referenced in the converted main.tf
- Use the target_cloud_name from the mapping for each variable name
- Use the target_cloud_type for types and defaults
- Preserve sensitive = true for passwords/secrets
- Add descriptions explaining the {target_cloud} context
- Output ONLY valid HCL, nothing else
"""

OUTPUTS_FILE_PROMPT = """Generate a complete outputs.tf for the {module_name} module
being converted from {source_cloud} to {target_cloud}.

ORIGINAL outputs.tf:
{original_outputs}

OUTPUT MAPPING (from project analysis):
{output_mapping}

The converted main.tf for this module contains these resources:
{converted_main_excerpt}

Rules:
- Each output must reference a real resource that exists in the converted main.tf
- Use target_cloud_equivalent names from the mapping
- Update resource type and attribute names to {target_cloud} conventions
- Output ONLY valid HCL, nothing else
"""

ROOT_MAIN_PROMPT = """Update this root main.tf from {source_cloud} to {target_cloud}.

ORIGINAL root main.tf:
{original_content}

MODULE WIRING MAP (exact variable renames for each module call):
{wiring_map}

ROOT LOCALS MAPPING:
{locals_map}

Rules:
- Update the provider block to {target_provider}
- For each module block, rename the variables passed using the wiring map above
- Update local values using the locals map
- Keep all module source paths exactly the same
- Output ONLY valid HCL, nothing else
"""

RETRY_PROMPT = """Convert ONLY this Terraform resource block.
From: {source_provider} resource type {src_type}
To:   {target_provider} resource type {tgt_type}

{block}

Output ONLY the converted HCL block:"""


# ── Understanding map helpers ────────────────────────────────────────────────

def _parse_understanding(state: ConversionState) -> Optional[Dict]:
    """Parse the project understanding JSON from state.conversion_plan."""
    if not state.conversion_plan:
        return None
    try:
        return json.loads(state.conversion_plan)
    except Exception:
        return None


def _get_module_understanding(understanding: Optional[Dict], module_name: str) -> Dict:
    """Get the understanding sub-dict for a specific module."""
    if not understanding:
        return {}
    return understanding.get("modules", {}).get(module_name, {})


def _build_variable_mapping_text(mod_understanding: Dict) -> str:
    """Format variable mapping for prompt injection."""
    variables = mod_understanding.get("variables", {})
    if not variables:
        return "No variable mapping available."
    lines = []
    for var_name, info in variables.items():
        target_name = info.get("target_cloud_name", var_name)
        target_type = info.get("target_cloud_type", "")
        purpose = info.get("purpose", "")
        lines.append(f"  {var_name} -> {target_name} ({target_type}) # {purpose}")
    return "\n".join(lines)


def _build_output_mapping_text(mod_understanding: Dict) -> str:
    """Format output mapping for prompt injection."""
    outputs = mod_understanding.get("outputs", {})
    if not outputs:
        return "No output mapping available."
    lines = []
    for out_name, info in outputs.items():
        target_equiv = info.get("target_cloud_equivalent", out_name)
        source = info.get("source_resource", "")
        purpose = info.get("purpose", "")
        lines.append(f"  {out_name} -> {target_equiv} (from {source}) # {purpose}")
    return "\n".join(lines)


def _build_wiring_map_text(understanding: Optional[Dict], direction) -> str:
    """Build the module wiring variable rename map for root main.tf."""
    if not understanding:
        return "No wiring map available."
    wiring = understanding.get("module_wiring", [])
    if not wiring:
        return "No cross-module wiring detected."
    lines = []
    for w in wiring:
        to_mod = w.get("to_module", "")
        old_var = w.get("input_variable", "")
        new_var = w.get("target_cloud_input", old_var)
        old_out = w.get("output_name", "")
        new_out = w.get("target_cloud_output", old_out)
        lines.append(
            f"  module.{to_mod}: variable '{old_var}' -> '{new_var}' "
            f"(receives output '{old_out}' -> '{new_out}')"
        )
    return "\n".join(lines)


def _build_locals_map_text(understanding: Optional[Dict]) -> str:
    """Build locals rename map for root main.tf."""
    if not understanding:
        return "No locals mapping available."
    locals_map = understanding.get("root_locals", {})
    if not locals_map:
        return "No locals detected."
    lines = []
    for name, info in locals_map.items():
        target_name = info.get("target_cloud_name", name)
        target_val = info.get("target_cloud_equivalent", info.get("value", ""))
        lines.append(f"  {name} -> {target_name} = \"{target_val}\"")
    return "\n".join(lines)


def _get_resource_attribute_map(mod_understanding: Dict, resource_type: str) -> str:
    """Get attribute mapping for a specific resource type."""
    resources = mod_understanding.get("resources", {})
    # Find by resource type prefix
    for key, info in resources.items():
        if resource_type in key:
            attrs = info.get("key_attributes", {})
            if attrs:
                return "\n".join(f"  {k} -> {v}" for k, v in attrs.items())
    return "Use standard mapping table."


def _get_dependency_context(mod_understanding: Dict, resource_type: str) -> str:
    """Get dependency context for a specific resource."""
    resources = mod_understanding.get("resources", {})
    for key, info in resources.items():
        if resource_type in key:
            deps = info.get("depends_on", [])
            if deps:
                return "Depends on: " + ", ".join(deps)
    return "No explicit dependencies."


# ── Block splitting ──────────────────────────────────────────────────────────

def _split_blocks(content: str) -> List[Tuple[str, str, str]]:
    blocks = []
    lines = content.splitlines(keepends=True)
    i, current, depth, in_block, header = 0, [], 0, False, ""
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not in_block:
            if stripped and not stripped.startswith("#") and "{" in line:
                in_block, header, depth, current = True, stripped, line.count("{") - line.count("}"), [line]
                if depth <= 0:
                    blocks.append(_classify(header, "".join(current)))
                    current, in_block, header = [], False, ""
            elif stripped:
                blocks.append(("other", "", line))
        else:
            current.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                blocks.append(_classify(header, "".join(current)))
                current, in_block, header, depth = [], False, "", 0
        i += 1
    if current:
        blocks.append(_classify(header, "".join(current)))
    return blocks


def _classify(header: str, text: str) -> Tuple[str, str, str]:
    parts = header.split()
    if not parts:
        return ("other", "", text)
    kw = parts[0].lower()
    if kw == "resource" and len(parts) >= 2:
        return ("resource", parts[1].strip('"'), text)
    if kw in ("variable", "output", "locals", "module", "data", "terraform", "provider"):
        return (kw, "", text)
    return ("other", "", text)


def _is_passthrough(original: str, result: str, source_prefix: str) -> bool:
    if not result.strip():
        return True
    if re.search(rf'resource\s+"({re.escape(source_prefix)}_[^"]+)"', result):
        return True
    a = re.sub(r"\s+", "", original)
    b = re.sub(r"\s+", "", result)
    if a and b and min(len(a), len(b)) / max(len(a), len(b)) > 0.85:
        return True
    return False


def _mechanical_replace(block: str, src_type: str, tgt_type: str,
                         src_prefix: str, tgt_prefix: str) -> str:
    result = block.replace(f'"{src_type}"', f'"{tgt_type}"')
    result = result.replace(f"{src_prefix}_", f"{tgt_prefix}_")
    return f"# TODO: mechanically converted from {src_type} — review required\n{result}"


def _strip_hint(text: str) -> str:
    first = text.split("\n")[0].strip().lower()
    if first in ("hcl", "terraform", "tf", "bicep"):
        text = "\n".join(text.split("\n")[1:]).strip()
    return text


def _compact_mapping(direction_key: str, source_prefix: str) -> str:
    table = get_mapping(direction_key)
    return "\n".join(
        f"  {s} -> {e['target']}"
        for s, e in table.items() if s.startswith(source_prefix)
    )


def _derive_exact_path(relative_path: str, output_dir: str) -> str:
    return str(Path(output_dir) / relative_path)


def _derive_suffixed_path(relative_path: str, output_dir: str, suffix: str) -> str:
    p = Path(relative_path)
    return str(Path(output_dir) / p.parent / (p.stem + suffix + ".tf"))


def _extract_target_resources(hcl: str, target_provider: str) -> list:
    pattern = rf'resource\s+"({re.escape(target_provider)}_[^"]+)"'
    return list(set(re.findall(pattern, hcl)))


# ── Per-block converter (understanding-informed) ─────────────────────────────

def _convert_resource_block(block_text: str, resource_type: str,
                              direction, mapping_str: str,
                              mod_understanding: Dict, llm) -> str:
    """Convert one resource block using understanding map for attribute guidance."""
    src_prefix = direction.source_provider
    tgt_prefix = direction.target_provider
    mapping = get_mapping(direction.key)
    tgt_type = mapping.get(resource_type, {}).get("target", "")
    attribute_map = _get_resource_attribute_map(mod_understanding, resource_type)
    dep_context = _get_dependency_context(mod_understanding, resource_type)

    result = _strip_hint(strip_markdown_fences(llm_call(llm, [
        HumanMessage(content=RESOURCE_BLOCK_PROMPT.format(
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            src_type=resource_type,
            tgt_type=tgt_type or f"{tgt_prefix}_equivalent",
            attribute_map=attribute_map,
            dependency_context=dep_context,
            block=block_text,
        )),
    ])))

    # Retry with simpler prompt if passthrough
    if _is_passthrough(block_text, result, src_prefix) and tgt_type:
        result = _strip_hint(strip_markdown_fences(llm_call(llm, [
            HumanMessage(content=RETRY_PROMPT.format(
                source_provider=src_prefix,
                target_provider=tgt_prefix,
                src_type=resource_type,
                tgt_type=tgt_type,
                block=block_text,
            )),
        ])))

    # Mechanical fallback
    if _is_passthrough(block_text, result, src_prefix) and tgt_type:
        result = _mechanical_replace(block_text, resource_type, tgt_type,
                                     src_prefix, tgt_prefix)
    return result


# ── File converters ──────────────────────────────────────────────────────────

def _convert_resource_file(file_info: FileInfo, direction, mapping_str: str,
                            mod_understanding: Dict, llm,
                            output_dir: str, suffix: str) -> ConvertedFile:
    blocks = _split_blocks(file_info.content)
    parts = [
        f"# Converted: {direction.source_cloud} -> {direction.target_cloud}\n"
        f"# Source: {file_info.relative_path}\n\n"
    ]
    for block_type, resource_type, block_text in blocks:
        if block_type == "resource":
            if resource_type.startswith(direction.source_provider + "_"):
                parts.append(
                    _convert_resource_block(block_text, resource_type, direction,
                                             mapping_str, mod_understanding, llm).rstrip()
                    + "\n\n"
                )
            else:
                parts.append(
                    f"# NOTE: '{resource_type}' kept as-is (not a {direction.source_cloud} resource)\n"
                    + block_text.rstrip() + "\n\n"
                )
        elif block_type in ("output", "locals", "terraform", "module", "data", "provider"):
            parts.append(block_text.rstrip() + "\n\n")
        elif block_type == "variable":
            parts.append(block_text.rstrip() + "\n\n")
        else:
            parts.append(block_text)

    target_content = "".join(parts)
    output_path = _derive_suffixed_path(file_info.relative_path, output_dir, suffix)
    return ConvertedFile(
        source_path=file_info.path,
        output_path=output_path,
        aws_content=target_content,
        resources_converted=_extract_target_resources(target_content, direction.target_provider),
    )


def _convert_variables_file(file_info: FileInfo, converted_main: str,
                              mod_understanding: Dict, direction, llm,
                              output_dir: str) -> ConvertedFile:
    var_mapping = _build_variable_mapping_text(mod_understanding)
    result = _strip_hint(strip_markdown_fences(llm_call(llm, [
        HumanMessage(content=VARIABLES_FILE_PROMPT.format(
            module_name=file_info.module_name or "root",
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            original_variables=file_info.content[:2000],
            variable_mapping=var_mapping,
            converted_main_excerpt=converted_main[:3000],
        )),
    ])))
    return ConvertedFile(
        source_path=file_info.path,
        output_path=_derive_exact_path(file_info.relative_path, output_dir),
        aws_content=result,
        resources_converted=[],
    )


def _convert_outputs_file(file_info: FileInfo, converted_main: str,
                           mod_understanding: Dict, direction, llm,
                           output_dir: str) -> ConvertedFile:
    out_mapping = _build_output_mapping_text(mod_understanding)
    result = _strip_hint(strip_markdown_fences(llm_call(llm, [
        HumanMessage(content=OUTPUTS_FILE_PROMPT.format(
            module_name=file_info.module_name or "root",
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            original_outputs=file_info.content[:2000],
            output_mapping=out_mapping,
            converted_main_excerpt=converted_main[:3000],
        )),
    ])))
    return ConvertedFile(
        source_path=file_info.path,
        output_path=_derive_exact_path(file_info.relative_path, output_dir),
        aws_content=result,
        resources_converted=[],
    )


def _convert_root_main(file_info: FileInfo, understanding: Optional[Dict],
                        direction, llm, output_dir: str) -> ConvertedFile:
    wiring_map = _build_wiring_map_text(understanding, direction)
    locals_map = _build_locals_map_text(understanding)
    result = _strip_hint(strip_markdown_fences(llm_call(llm, [
        HumanMessage(content=ROOT_MAIN_PROMPT.format(
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            target_provider=direction.target_provider,
            original_content=file_info.content[:5000],
            wiring_map=wiring_map,
            locals_map=locals_map,
        )),
    ])))
    return ConvertedFile(
        source_path=file_info.path,
        output_path=_derive_exact_path(file_info.relative_path, output_dir),
        aws_content=result,
        resources_converted=[],
    )


# ── Main agent ───────────────────────────────────────────────────────────────

def converter_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: convert all files using the project understanding map.

    Pass 1 — Convert resource/main.tf files (block by block, understanding-informed)
    Pass 2 — Regenerate variables.tf per module using variable mapping from understanding
    Pass 3 — Regenerate outputs.tf per module using output mapping from understanding
    Pass 4 — Update root main.tf module blocks using module_wiring map
    Pass 5 — Pass through provider/backend files with provider name swapped
    """
    if not state.discovered_files:
        return state

    direction = get_direction(state.direction)
    mapping_str = _compact_mapping(state.direction, direction.source_provider)
    suffix = direction.output_suffix
    understanding = _parse_understanding(state)

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
        base_url=state.base_url,
    )

    converted = []
    failed = []

    # Separate files by role
    resource_files, variables_files, outputs_files = [], [], []
    root_main_files, passthrough_files = [], []

    for f in state.discovered_files:
        is_root = (f.module_name == "root")
        if f.file_role in ("resource", "main"):
            if is_root and state.is_module_project:
                root_main_files.append(f)
            else:
                resource_files.append(f)
        elif f.file_role == "variables":
            variables_files.append(f)
        elif f.file_role == "outputs":
            outputs_files.append(f)
        else:
            passthrough_files.append(f)

    # ── Pass 1: Convert resource/main files ───────────────────────────
    converted_mains: Dict[str, str] = {}
    for f in resource_files:
        try:
            mod_u = _get_module_understanding(understanding, f.module_name)
            cf = _convert_resource_file(f, direction, mapping_str, mod_u,
                                         llm, state.output_dir, suffix)
            converted.append(cf)
            converted_mains[f.module_name] = cf.aws_content
        except Exception as exc:
            failed.append(f"{f.relative_path}: {exc}")

    # ── Pass 2: Regenerate variables.tf using understanding map ────────
    for f in variables_files:
        try:
            mod_u = _get_module_understanding(understanding, f.module_name)
            main_content = converted_mains.get(f.module_name, f.content)
            cf = _convert_variables_file(f, main_content, mod_u, direction,
                                          llm, state.output_dir)
            converted.append(cf)
        except Exception as exc:
            failed.append(f"{f.relative_path} (variables): {exc}")

    # ── Pass 3: Regenerate outputs.tf using understanding map ──────────
    for f in outputs_files:
        try:
            mod_u = _get_module_understanding(understanding, f.module_name)
            main_content = converted_mains.get(f.module_name, f.content)
            cf = _convert_outputs_file(f, main_content, mod_u, direction,
                                        llm, state.output_dir)
            converted.append(cf)
        except Exception as exc:
            failed.append(f"{f.relative_path} (outputs): {exc}")

    # ── Pass 4: Update root main.tf with wiring map ────────────────────
    for f in root_main_files:
        try:
            cf = _convert_root_main(f, understanding, direction, llm, state.output_dir)
            converted.append(cf)
        except Exception as exc:
            failed.append(f"{f.relative_path} (root main): {exc}")

    # Non-module projects: convert root main.tf as resource file
    if not state.is_module_project:
        for f in root_main_files:
            try:
                mod_u = _get_module_understanding(understanding, "root")
                cf = _convert_resource_file(f, direction, mapping_str, mod_u,
                                             llm, state.output_dir, suffix)
                converted.append(cf)
            except Exception as exc:
                failed.append(f"{f.relative_path}: {exc}")

    # ── Pass 5: Passthrough provider/backend with provider swap ───────
    for f in passthrough_files:
        try:
            content = f.content.replace(
                f'provider "{direction.source_provider}"',
                f'provider "{direction.target_provider}"'
            )
            converted.append(ConvertedFile(
                source_path=f.path,
                output_path=_derive_exact_path(f.relative_path, state.output_dir),
                aws_content=content,
            ))
        except Exception as exc:
            failed.append(f"{f.relative_path} (passthrough): {exc}")

    state.converted_files = state.converted_files + converted
    state.failed_files = state.failed_files + failed
    return state
