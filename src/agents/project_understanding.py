"""
Agent 2b – Project Understanding Agent

Reads the entire codebase holistically before any conversion happens.
Builds a complete picture of:
  - What every variable in every variables.tf is used for
  - What every output in every outputs.tf exposes and where it comes from
  - How module calls in root main.tf wire outputs → inputs across modules
  - Which resources depend on which other resources
  - The full data flow: root → module → resource → output → root → next module

This context is stored in state and passed to the converter so it can make
accurate, relationship-aware decisions instead of converting files in isolation.
"""
import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction

SYSTEM_PROMPT = """You are an expert Terraform architect who deeply understands
infrastructure code structure, module composition, and variable/output wiring.
Your job is to analyse a complete Terraform codebase and produce a precise
dependency and data-flow map that will guide a cloud migration.
Always respond with valid JSON only. No markdown, no explanation outside the JSON."""

UNDERSTANDING_PROMPT = """Analyse this complete Terraform codebase and return a JSON object
that maps the FULL data flow: how variables, outputs, and resources connect across modules.

The codebase is being migrated from {source_cloud} to {target_cloud}.

FILES:
{all_files_content}

Return this exact JSON structure:
{{
  "modules": {{
    "<module_name>": {{
      "path": "<directory path>",
      "purpose": "<what this module does in one sentence>",
      "variables": {{
        "<var_name>": {{
          "type": "<type>",
          "purpose": "<what this variable controls>",
          "used_by_resources": ["<resource_type.name>", ...],
          "target_cloud_name": "<suggested variable name in {target_cloud}>",
          "target_cloud_type": "<suggested type/value in {target_cloud}>"
        }}
      }},
      "outputs": {{
        "<output_name>": {{
          "source_resource": "<resource_type.name.attribute>",
          "purpose": "<what this exposes>",
          "consumed_by_modules": ["<module_name>", ...],
          "target_cloud_equivalent": "<what this maps to in {target_cloud}>"
        }}
      }},
      "resources": {{
        "<resource_type.name>": {{
          "target_resource_type": "<equivalent {target_cloud} resource type>",
          "depends_on": ["<resource_type.name>", ...],
          "key_attributes": {{
            "<aws_attribute>": "<gcp_equivalent_attribute>"
          }}
        }}
      }}
    }}
  }},
  "module_wiring": [
    {{
      "from_module": "<module_name>",
      "output_name": "<output_name>",
      "to_module": "<module_name>",
      "input_variable": "<variable_name>",
      "target_cloud_output": "<new output name in {target_cloud}>",
      "target_cloud_input": "<new variable name in {target_cloud}>"
    }}
  ],
  "root_locals": {{
    "<local_name>": {{
      "value": "<current value>",
      "target_cloud_equivalent": "<suggested value in {target_cloud}>",
      "target_cloud_name": "<suggested name in {target_cloud}>"
    }}
  }},
  "conversion_notes": ["<important migration note>", ...]
}}"""


def _build_all_files_content(state: ConversionState) -> str:
    """Concatenate all discovered files with clear headers."""
    parts = []
    for f in state.discovered_files:
        parts.append(f"=== FILE: {f.relative_path} (module: {f.module_name}, role: {f.file_role}) ===")
        parts.append(f.content)
        parts.append("")
    return "\n".join(parts)


def project_understanding_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: build a complete understanding of the project structure
    before any conversion begins.
    """
    if not state.discovered_files:
        state.warnings.append("Project understanding skipped — no files found.")
        return state

    direction = get_direction(state.direction)
    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
        base_url=state.base_url,
    )

    all_files = _build_all_files_content(state)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=UNDERSTANDING_PROMPT.format(
            source_cloud=direction.source_cloud,
            target_cloud=direction.target_cloud,
            all_files_content=all_files[:12000],  # context window safety
        )),
    ]

    try:
        raw = llm_call(llm, messages)
        raw = strip_markdown_fences(raw)
        understanding: Dict[str, Any] = json.loads(raw)

        # Store the full understanding in conversion_plan as structured JSON
        # so every downstream agent can access it
        state.conversion_plan = json.dumps(understanding, indent=2)

        # Also extract a human-readable summary for the report
        notes = understanding.get("conversion_notes", [])
        if notes:
            state.warnings.extend(notes)

        # Build module wiring summary for warnings/report
        wiring = understanding.get("module_wiring", [])
        if wiring:
            state.warnings.append(
                f"Module wiring detected: {len(wiring)} cross-module variable connections mapped."
            )

    except json.JSONDecodeError as exc:
        # Fallback: store raw text — converter can still use it as context
        state.warnings.append(
            f"Project understanding: JSON parse failed ({exc}). "
            "Using raw analysis as context."
        )
        state.conversion_plan = raw[:8000] if 'raw' in dir() else ""
    except Exception as exc:
        state.errors.append(f"Project understanding failed: {exc}")

    return state
