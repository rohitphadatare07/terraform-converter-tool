"""
Agent 3 – IaC Converter
Direction-aware: builds system prompt and convert prompt dynamically
from the conversion direction and resource mapping table.
"""
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState, ConvertedFile
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction
from src.mappings import mapping_to_prompt_text

SYSTEM_PROMPT_TEMPLATE = """You are a senior DevOps/Cloud engineer specialising in
multi-cloud infrastructure migration.

Task: Convert {source_label} Infrastructure-as-Code to {target_label} Terraform HCL.

Rules:
1. Output ONLY valid HCL Terraform – no explanations, no markdown fences.
2. Replace every {source_cloud} resource with its {target_cloud} equivalent.
3. Preserve logical naming conventions.
4. Use Terraform best practices: variables, locals, data sources.
5. Add inline comments (# ...) where the mapping is non-trivial.
6. If a resource has no direct equivalent, create a commented stub with a TODO.
7. Do NOT include the provider block – generated separately.
8. Use the standard variables: {standard_vars}

{source_cloud} → {target_cloud} resource mapping:
{mapping_table}
"""

CONVERT_PROMPT_TEMPLATE = """Convert the following {source_cloud} IaC file to {target_cloud} Terraform HCL.

Source file: {relative_path}
File type: {file_type}

--- BEGIN SOURCE ---
{content}
--- END SOURCE ---

Conversion plan context:
{conversion_plan}

Output ONLY the converted Terraform HCL:
"""


def _extract_target_resources(hcl: str, target_provider: str) -> list:
    """Extract target resource type strings from HCL output."""
    pattern = rf'resource\s+"({re.escape(target_provider)}_[^"]+)"'
    return list(set(re.findall(pattern, hcl)))


def _derive_output_path(relative_path: str, output_dir: str, suffix: str) -> str:
    """Mirror source directory structure; append direction suffix to filename."""
    p = Path(relative_path)
    new_name = p.stem + suffix + ".tf"
    return str(Path(output_dir) / p.parent / new_name)


def converter_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: convert all discovered files to target cloud Terraform."""
    if not state.discovered_files:
        return state

    direction = get_direction(state.direction)
    mapping_table = mapping_to_prompt_text(state.direction)
    standard_vars = ", ".join(f"var.{v}" for v in direction.standard_vars)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        source_label=direction.source_label,
        target_label=direction.target_label,
        source_cloud=direction.source_cloud,
        target_cloud=direction.target_cloud,
        standard_vars=standard_vars,
        mapping_table=mapping_table,
    )

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
            convert_prompt = CONVERT_PROMPT_TEMPLATE.format(
                source_cloud=direction.source_cloud,
                target_cloud=direction.target_cloud,
                relative_path=file_info.relative_path,
                file_type=file_info.file_type,
                content=file_info.content[:8000],
                conversion_plan=state.conversion_plan[:2000],
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=convert_prompt),
            ]

            response = llm_call(llm, messages)
            target_content = strip_markdown_fences(response)

            # Strip accidental leading language hint lines
            first_line = target_content.split("\n")[0].strip().lower()
            if first_line in ("hcl", "terraform", "tf", "bicep"):
                target_content = "\n".join(target_content.split("\n")[1:]).strip()

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
