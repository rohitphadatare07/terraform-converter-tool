"""
Agent 4 – Post-Processor
Generates the supporting Terraform files:
  - provider.tf   (AWS provider block)
  - variables.tf  (all common variables)
  - outputs.tf    (key output values)
  - backend.tf    (optional remote state)
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState
from src.llm.factory import get_llm

SYSTEM_PROMPT = """You are a senior Terraform engineer. You write clean, idiomatic AWS Terraform.
Output ONLY raw HCL – no markdown, no backticks, no explanations."""

PROVIDER_TF_PROMPT = """Generate an AWS provider.tf file for the following infrastructure.

Converted AWS resources (sample):
{resources_list}

Requirements:
- AWS provider version ~> 5.0
- Use var.aws_region (default = "us-east-1")
- Use var.aws_account_id
- Include required_version >= "1.5.0"
- Include default_tags block with project, environment, managed_by = "terraform" tags

Output ONLY the HCL:
"""

VARIABLES_TF_PROMPT = """Generate a variables.tf file for the following AWS Terraform infrastructure.

Resources being created:
{resources_list}

Conversion plan context:
{conversion_plan}

Include at minimum:
- aws_region
- aws_account_id
- project_name
- environment (dev/staging/prod)
- Any variables referenced in the resources list

Output ONLY the HCL:
"""

OUTPUTS_TF_PROMPT = """Generate an outputs.tf file for the following AWS Terraform infrastructure.

Converted resources:
{resources_list}

Expose the most important outputs like VPC ID, subnet IDs, EKS cluster endpoint,
RDS endpoint, S3 bucket names, etc. Only output values for resources that actually exist.

Output ONLY the HCL:
"""


def _collect_all_resources(state: ConversionState) -> str:
    """Build a compact list of all AWS resource types from converted files."""
    all_resources = []
    for f in state.converted_files:
        all_resources.extend(f.resources_converted)
    unique = sorted(set(all_resources))
    return "\n".join(f"  - {r}" for r in unique) if unique else "  (no resources detected)"


def postprocessor_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: generate provider.tf, variables.tf, outputs.tf.
    """
    if not state.converted_files:
        state.warnings.append("Post-processor skipped – no converted files.")
        return state

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
    )

    resources_list = _collect_all_resources(state)
    plan_snippet = state.conversion_plan[:1500]

    # ── provider.tf ────────────────────────────────────────────────────
    try:
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=PROVIDER_TF_PROMPT.format(resources_list=resources_list)),
        ])
        state.provider_tf = _strip_fences(resp.content)
    except Exception as exc:
        state.errors.append(f"Post-processor: provider.tf failed – {exc}")
        state.provider_tf = _fallback_provider_tf()

    # ── variables.tf ───────────────────────────────────────────────────
    try:
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=VARIABLES_TF_PROMPT.format(
                resources_list=resources_list,
                conversion_plan=plan_snippet,
            )),
        ])
        state.variables_tf = _strip_fences(resp.content)
    except Exception as exc:
        state.errors.append(f"Post-processor: variables.tf failed – {exc}")
        state.variables_tf = _fallback_variables_tf()

    # ── outputs.tf ────────────────────────────────────────────────────
    try:
        resp = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=OUTPUTS_TF_PROMPT.format(resources_list=resources_list)),
        ])
        state.outputs_tf = _strip_fences(resp.content)
    except Exception as exc:
        state.errors.append(f"Post-processor: outputs.tf failed – {exc}")
        state.outputs_tf = "# outputs.tf – generation failed, please fill manually\n"

    # ── backend.tf (static template) ──────────────────────────────────
    state.backend_tf = _backend_tf_template()

    return state


# ── Helpers ────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        first_line = text.split("\n")[0].strip()
        if first_line in ("hcl", "terraform", "tf"):
            text = "\n".join(text.splitlines()[1:])
    return text.strip()


def _fallback_provider_tf() -> str:
    return '''terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project    = var.project_name
      ManagedBy  = "terraform"
    }
  }
}
'''


def _fallback_variables_tf() -> str:
    return '''variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}
'''


def _backend_tf_template() -> str:
    return '''# backend.tf – Uncomment and configure to use remote state (recommended for production)
#
# terraform {
#   backend "s3" {
#     bucket         = "<YOUR_STATE_BUCKET>"
#     key            = "terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "<YOUR_LOCK_TABLE>"
#     encrypt        = true
#   }
# }
'''
