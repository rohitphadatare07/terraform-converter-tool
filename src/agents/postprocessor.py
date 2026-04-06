"""
Agent 4 – Post-Processor
Generates provider.tf, variables.tf, outputs.tf and backend.tf
for the target cloud. Fully direction-aware.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState
from src.llm.factory import get_llm
from src.llm.call import llm_call, strip_markdown_fences
from src.directions import get_direction

SYSTEM_PROMPT = "You are a senior Terraform engineer. Output ONLY raw HCL – no markdown, no backticks."

PROVIDER_PROMPT = """Generate a provider.tf for {target_label} Terraform.

Target resources being created:
{resources_list}

Requirements:
- Use {target_provider} provider, latest stable version constraint (~> X.0)
- All configurable values must use variables (no hardcoded account IDs, regions, etc.)
- Include required_version >= "1.5.0"
- Include default_tags or equivalent tagging block
- Standard variables: {standard_vars}

Output ONLY the HCL:
"""

VARIABLES_PROMPT = """Generate a variables.tf for {target_label} Terraform.

Resources being created:
{resources_list}

Conversion plan context:
{conversion_plan}

Include at minimum these standard variables with sensible defaults:
{standard_vars}

Plus any additional variables inferred from the resource list.

Output ONLY the HCL:
"""

OUTPUTS_PROMPT = """Generate an outputs.tf for {target_label} Terraform.

Resources created:
{resources_list}

Expose the most important outputs (endpoints, IDs, ARNs, connection strings).
Only output values for resources that actually exist in the list above.

Output ONLY the HCL:
"""

# ── Cloud-specific provider block templates ────────────────────────────────

PROVIDER_TEMPLATES = {
    "aws": '''terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.aws_region
  default_tags {{
    tags = {{
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }}
  }}
}}
''',
    "google": '''terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.gcp_project_id
  region  = var.gcp_region
}}
''',
    "azurerm": '''terraform {{
  required_version = ">= 1.5.0"
  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }}
  }}
}}

provider "azurerm" {{
  features {{}}
  subscription_id = var.azure_subscription_id
}}
''',
}

BACKEND_TEMPLATES = {
    "aws": '''# backend.tf – configure S3 remote state (recommended for production)
#
# terraform {{
#   backend "s3" {{
#     bucket         = "<YOUR_STATE_BUCKET>"
#     key            = "terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "<YOUR_LOCK_TABLE>"
#     encrypt        = true
#   }}
# }}
''',
    "google": '''# backend.tf – configure GCS remote state (recommended for production)
#
# terraform {{
#   backend "gcs" {{
#     bucket = "<YOUR_STATE_BUCKET>"
#     prefix = "terraform/state"
#   }}
# }}
''',
    "azurerm": '''# backend.tf – configure Azure Storage remote state (recommended for production)
#
# terraform {{
#   backend "azurerm" {{
#     resource_group_name  = "<RESOURCE_GROUP>"
#     storage_account_name = "<STORAGE_ACCOUNT>"
#     container_name       = "tfstate"
#     key                  = "terraform.tfstate"
#   }}
# }}
''',
}


def _collect_resources(state: ConversionState) -> str:
    all_res = []
    for f in state.converted_files:
        all_res.extend(f.resources_converted)
    unique = sorted(set(all_res))
    return "\n".join(f"  - {r}" for r in unique) if unique else "  (no resources detected)"


def postprocessor_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: generate provider.tf, variables.tf, outputs.tf."""
    if not state.converted_files:
        state.warnings.append("Post-processor skipped – no converted files.")
        return state

    direction = get_direction(state.direction)
    target_provider = direction.target_provider
    standard_vars = "\n".join(f"  - {v}" for v in direction.standard_vars)

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
        base_url=state.base_url,
    )

    resources_list = _collect_resources(state)
    plan_snippet = state.conversion_plan[:1500]

    # ── provider.tf ────────────────────────────────────────────────────
    try:
        resp = llm_call(llm, [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=PROVIDER_PROMPT.format(
                target_label=direction.target_label,
                target_provider=target_provider,
                resources_list=resources_list,
                standard_vars=standard_vars,
            )),
        ])
        state.provider_tf = strip_markdown_fences(resp)
    except Exception as exc:
        state.errors.append(f"Post-processor: provider.tf failed – {exc}")
        state.provider_tf = PROVIDER_TEMPLATES.get(target_provider, "# provider.tf – fill manually\n")

    # ── variables.tf ───────────────────────────────────────────────────
    try:
        resp = llm_call(llm, [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=VARIABLES_PROMPT.format(
                target_label=direction.target_label,
                resources_list=resources_list,
                conversion_plan=plan_snippet,
                standard_vars=standard_vars,
            )),
        ])
        state.variables_tf = strip_markdown_fences(resp)
    except Exception as exc:
        state.errors.append(f"Post-processor: variables.tf failed – {exc}")
        state.variables_tf = "# variables.tf – generation failed, fill manually\n"

    # ── outputs.tf ────────────────────────────────────────────────────
    try:
        resp = llm_call(llm, [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=OUTPUTS_PROMPT.format(
                target_label=direction.target_label,
                resources_list=resources_list,
            )),
        ])
        state.outputs_tf = strip_markdown_fences(resp)
    except Exception as exc:
        state.errors.append(f"Post-processor: outputs.tf failed – {exc}")
        state.outputs_tf = "# outputs.tf – generation failed, fill manually\n"

    # ── backend.tf (static template, no LLM needed) ───────────────────
    state.backend_tf = BACKEND_TEMPLATES.get(
        target_provider,
        "# backend.tf – configure remote state\n"
    )

    return state
