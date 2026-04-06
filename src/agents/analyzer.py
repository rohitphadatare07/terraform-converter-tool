"""
Agent 2 – Infrastructure Analyzer
Direction-aware: builds analysis prompt dynamically from the
conversion direction and resource mapping table.
"""
import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction
from src.mappings import mapping_to_prompt_text

SYSTEM_PROMPT = """You are an expert cloud infrastructure architect specialising in
multi-cloud migrations. Your task is to analyze Infrastructure-as-Code (IaC) files
and produce a structured migration analysis in JSON.

Always respond with valid JSON only. No markdown, no explanation outside the JSON."""

ANALYSIS_PROMPT = """You are converting {source_label} IaC to {target_label} Terraform.

Resource mapping reference ({source_cloud} → {target_cloud}):
{mapping_table}

Analyze the following source files and return a JSON object:

{{
  "resource_summary": {{
    "<source_resource_type>": {{
      "count": <int>,
      "target_equivalent": "<target_resource_type>",
      "conversion_complexity": "simple|moderate|complex",
      "notes": "<migration notes>"
    }}
  }},
  "dependencies": {{
    "<resource_name>": ["<depends_on_1>", "..."]
  }},
  "conversion_plan": "<detailed step-by-step strategy>",
  "estimated_target_resources": ["<list of target resource types>"],
  "risks": ["<migration risks or caveats>"]
}}

Source files:
---
{files_summary}
---
"""


def _build_files_summary(state: ConversionState) -> str:
    lines = []
    for f in state.discovered_files:
        lines.append(f"### File: {f.relative_path} (type: {f.file_type})")
        if f.resource_types:
            lines.append(f"Resources found: {', '.join(f.resource_types)}")
        content_lines = f.content.splitlines()[:200]
        lines.append("```")
        lines.extend(content_lines)
        if len(f.content.splitlines()) > 200:
            lines.append("... [truncated]")
        lines.append("```\n")
    return "\n".join(lines)


def analyzer_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: analyse discovered files and produce a conversion plan."""
    if not state.discovered_files:
        state.warnings.append("Analyzer skipped – no files to analyse.")
        return state

    direction = get_direction(state.direction)

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
        base_url=state.base_url,
    )

    files_summary = _build_files_summary(state)
    mapping_table = mapping_to_prompt_text(state.direction)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=ANALYSIS_PROMPT.format(
            source_label=direction.source_label,
            target_label=direction.target_label,
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            mapping_table=mapping_table,
            files_summary=files_summary,
        )),
    ]

    try:
        raw = llm_call(llm, messages)
        raw = strip_markdown_fences(raw)
        data: Dict[str, Any] = json.loads(raw)

        state.gcp_resource_summary = data.get("resource_summary", {})
        state.resource_dependency_map = data.get("dependencies", {})
        state.conversion_plan = data.get("conversion_plan", "")

        risks = data.get("risks", [])
        if risks:
            state.warnings.extend(risks)

    except json.JSONDecodeError as exc:
        state.errors.append(f"Analyzer: JSON parse error – {exc}. Raw: {raw[:300]}")
    except Exception as exc:
        state.errors.append(f"Analyzer: LLM call failed – {exc}")

    return state
