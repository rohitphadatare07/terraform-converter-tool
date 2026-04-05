"""
Agent 2 – GCP Infrastructure Analyzer
Uses the LLM to analyse discovered files, build a resource summary,
and produce a conversion plan before any code is generated.
"""
import json
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState
from src.llm.factory import get_llm

SYSTEM_PROMPT = """You are an expert cloud infrastructure architect with deep knowledge of
both Google Cloud Platform (GCP) and Amazon Web Services (AWS). Your task is to analyze
GCP Infrastructure-as-Code (IaC) and produce a structured migration analysis.

Always respond with valid JSON. No markdown, no explanation outside the JSON object."""

ANALYSIS_PROMPT = """Analyze the following GCP infrastructure files and return a JSON object with:

{{
  "resource_summary": {{
    "<gcp_resource_type>": {{
      "count": <int>,
      "aws_equivalent": "<aws_resource_type>",
      "conversion_complexity": "simple|moderate|complex",
      "notes": "<any important migration notes>"
    }}
  }},
  "dependencies": {{
    "<resource_name>": ["<depends_on_resource_1>", "..."]
  }},
  "conversion_plan": "<detailed step-by-step conversion strategy as a string>",
  "estimated_aws_resources": ["<list of AWS resource types that will be created>"],
  "risks": ["<list of migration risks or caveats>"]
}}

Files to analyze:
---
{files_summary}
---
"""


def _build_files_summary(state: ConversionState) -> str:
    """Build a compact text summary of all discovered files for the LLM prompt."""
    lines = []
    for f in state.discovered_files:
        lines.append(f"### File: {f.relative_path} (type: {f.file_type})")
        if f.resource_types:
            lines.append(f"GCP resources found: {', '.join(f.resource_types)}")
        # Include up to 200 lines of content to stay within context limits
        content_lines = f.content.splitlines()[:200]
        lines.append("```")
        lines.extend(content_lines)
        if len(f.content.splitlines()) > 200:
            lines.append("... [truncated]")
        lines.append("```\n")
    return "\n".join(lines)


def analyzer_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: analyse all discovered GCP files and produce a plan.
    """
    if not state.discovered_files:
        state.warnings.append("Analyzer skipped – no files to analyse.")
        return state

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
    )

    files_summary = _build_files_summary(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=ANALYSIS_PROMPT.format(files_summary=files_summary)
        ),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()

        # Strip possible markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

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