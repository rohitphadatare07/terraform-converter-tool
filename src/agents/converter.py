"""
Agent 3 – IaC Converter
Direction-aware converter with:
- Small-model-friendly prompts (one resource block at a time)
- Passthrough detection (catches when LLM returns source unchanged)
- Retry with simplified prompt on failure
- Mechanical fallback replace if LLM still fails
"""
import re
from pathlib import Path
from typing import List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState, ConvertedFile
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction
from src.mappings import get_mapping

# ── Prompts ────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Terraform migration expert.
Convert {source_cloud} Terraform resource blocks to {target_cloud} Terraform.
Output ONLY raw HCL. No explanation. No markdown. No backticks.

MAPPING ({source_cloud} -> {target_cloud}):
{mapping_table}"""

BLOCK_PROMPT = """Convert this single {source_cloud} resource block to {target_cloud}.
Use the mapping table. Output ONLY the converted HCL block.

SOURCE BLOCK:
{block}

CONVERTED {target_cloud} BLOCK:"""

RETRY_PROMPT = """Convert this Terraform resource from {source_provider} to {target_provider}.

Input:
{block}

Rules:
- Change resource "{source_provider}_<type>" to resource "{target_provider}_<type>"
- Use this mapping: {src_type} -> {tgt_type}
- Output ONLY the HCL block. No explanation.

Output:"""


# ── Block splitter ─────────────────────────────────────────────────────────

def _split_resource_blocks(content: str) -> List[Tuple[str, str, str]]:
    """Split HCL into (block_type, resource_type, text) tuples."""
    blocks = []
    lines = content.splitlines(keepends=True)
    i = 0
    current = []
    depth = 0
    in_block = False
    header = ""

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not in_block:
            if stripped and not stripped.startswith("#") and "{" in line:
                in_block = True
                header = stripped
                depth = line.count("{") - line.count("}")
                current = [line]
                if depth <= 0:
                    blocks.append(_classify(header, "".join(current)))
                    current = []
                    in_block = False
                    header = ""
            elif stripped:
                blocks.append(("other", "", line))
        else:
            current.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                blocks.append(_classify(header, "".join(current)))
                current = []
                in_block = False
                header = ""
                depth = 0
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
    if kw in ("variable", "output", "locals", "module", "data", "terraform"):
        return (kw, "", text)
    return ("other", "", text)


# ── Passthrough detection ──────────────────────────────────────────────────

def _is_passthrough(original: str, result: str, source_prefix: str) -> bool:
    """True if LLM returned the source essentially unchanged."""
    if not result.strip():
        return True
    # Source-cloud resource types still present
    if re.search(rf'resource\s+"({re.escape(source_prefix)}_[^"]+)"', result):
        return True
    # Near-identical content
    a = re.sub(r"\s+", "", original)
    b = re.sub(r"\s+", "", result)
    if a and b and min(len(a), len(b)) / max(len(a), len(b)) > 0.85:
        return True
    return False


# ── Mechanical fallback ────────────────────────────────────────────────────

def _mechanical_replace(block: str, src_type: str, tgt_type: str,
                         src_prefix: str, tgt_prefix: str) -> str:
    """Last-resort string substitution with TODO comment."""
    result = block.replace(f'"{src_type}"', f'"{tgt_type}"')
    result = result.replace(f"{src_prefix}_", f"{tgt_prefix}_")
    return f"# TODO: mechanically converted from {src_type} — review required\n{result}"


# ── Single block converter ─────────────────────────────────────────────────

def _convert_block(block_text: str, resource_type: str, direction,
                   mapping_str: str, llm) -> str:
    """Convert one resource block with retry and mechanical fallback."""
    src_prefix = direction.source_provider
    tgt_prefix = direction.target_provider
    mapping = get_mapping(direction.key)
    tgt_type = mapping.get(resource_type, {}).get("target", "")

    sys_msg = SystemMessage(content=SYSTEM_PROMPT.format(
        source_cloud=direction.source_cloud,
        target_cloud=direction.target_cloud,
        mapping_table=mapping_str,
    ))

    # Attempt 1 — standard prompt
    result = strip_markdown_fences(llm_call(llm, [
        sys_msg,
        HumanMessage(content=BLOCK_PROMPT.format(
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            block=block_text,
        )),
    ]))
    result = _strip_hint(result)

    # Attempt 2 — simpler explicit retry
    if _is_passthrough(block_text, result, src_prefix) and tgt_type:
        result = strip_markdown_fences(llm_call(llm, [
            HumanMessage(content=RETRY_PROMPT.format(
                source_provider=src_prefix,
                target_provider=tgt_prefix,
                block=block_text,
                src_type=resource_type,
                tgt_type=tgt_type,
            )),
        ]))
        result = _strip_hint(result)

    # Attempt 3 — mechanical replace
    if _is_passthrough(block_text, result, src_prefix) and tgt_type:
        result = _mechanical_replace(block_text, resource_type, tgt_type,
                                     src_prefix, tgt_prefix)

    return result


def _strip_hint(text: str) -> str:
    """Remove leading language hint line like 'hcl' or 'terraform'."""
    first = text.split("\n")[0].strip().lower()
    if first in ("hcl", "terraform", "tf", "bicep"):
        text = "\n".join(text.split("\n")[1:]).strip()
    return text


# ── Helpers ────────────────────────────────────────────────────────────────

def _derive_output_path(relative_path: str, output_dir: str, suffix: str) -> str:
    p = Path(relative_path)
    return str(Path(output_dir) / p.parent / (p.stem + suffix + ".tf"))


def _extract_target_resources(hcl: str, target_provider: str) -> list:
    pattern = rf'resource\s+"({re.escape(target_provider)}_[^"]+)"'
    return list(set(re.findall(pattern, hcl)))


def _compact_mapping(direction_key: str, source_prefix: str) -> str:
    """Compact mapping string — only lines relevant to source prefix."""
    table = get_mapping(direction_key)
    lines = [f"  {s} -> {e['target']}"
             for s, e in table.items() if s.startswith(source_prefix)]
    return "\n".join(lines)


# ── Main agent node ────────────────────────────────────────────────────────

def converter_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: convert all discovered files block by block.

    Each resource block is sent to the LLM individually — this is critical
    for small models like qwen2:1.5b that lose instruction-following on
    large prompts. Passthrough responses trigger a retry then a mechanical
    fallback so the output is never silently wrong.
    """
    if not state.discovered_files:
        return state

    direction = get_direction(state.direction)
    mapping_str = _compact_mapping(state.direction, direction.source_provider)

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
        base_url=state.base_url,
    )

    converted = []
    failed = []

    for file_info in state.discovered_files:
        try:
            blocks = _split_resource_blocks(file_info.content)
            parts = [
                f"# Converted: {direction.source_cloud} -> {direction.target_cloud}\n"
                f"# Source: {file_info.relative_path}\n\n"
            ]

            for block_type, resource_type, block_text in blocks:

                if block_type == "resource":
                    if resource_type.startswith(direction.source_provider + "_"):
                        # Source-cloud resource — convert it
                        parts.append(
                            _convert_block(block_text, resource_type,
                                           direction, mapping_str, llm).rstrip()
                            + "\n\n"
                        )
                    else:
                        # Different provider — keep with note
                        parts.append(
                            f"# NOTE: '{resource_type}' is not a "
                            f"{direction.source_cloud} resource — kept as-is\n"
                            + block_text.rstrip() + "\n\n"
                        )

                elif block_type == "variable":
                    parts.append(
                        "# NOTE: review variable defaults for "
                        f"{direction.target_cloud}\n"
                        + block_text.rstrip() + "\n\n"
                    )

                elif block_type in ("output", "locals", "terraform", "module", "data"):
                    parts.append(block_text.rstrip() + "\n\n")

                else:
                    parts.append(block_text)

            target_content = "".join(parts)
            output_path = _derive_output_path(
                file_info.relative_path, state.output_dir, direction.output_suffix
            )
            resources = _extract_target_resources(target_content, direction.target_provider)

            converted.append(ConvertedFile(
                source_path=file_info.path,
                output_path=output_path,
                aws_content=target_content,
                resources_converted=resources,
            ))

        except Exception as exc:
            failed.append(f"{file_info.relative_path}: {exc}")

    state.converted_files = state.converted_files + converted
    state.failed_files = state.failed_files + failed
    return state