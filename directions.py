"""
Conversion Direction Registry
==============================
Single source of truth for all supported cloud-to-cloud IaC conversion directions.

Adding a new direction requires only:
  1. Adding an entry to DIRECTIONS dict below
  2. Adding a mapping file in src/mappings/<direction>.py

Everything else (CLI, pipeline, agents, prompts) is fully dynamic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Direction:
    """Describes one conversion direction."""
    key: str                    # e.g. "gcp-aws"
    source_cloud: str           # e.g. "GCP"
    target_cloud: str           # e.g. "AWS"
    source_provider: str        # Terraform provider prefix, e.g. "google"
    target_provider: str        # Terraform provider prefix, e.g. "aws"
    source_label: str           # Human label e.g. "Google Cloud"
    target_label: str           # Human label e.g. "Amazon Web Services"
    output_suffix: str          # Appended to converted filenames e.g. "_aws"
    # Terraform provider block template for the target cloud
    provider_template: str = ""
    # Standard variable names expected in generated files
    standard_vars: List[str] = field(default_factory=list)


# ── All 6 supported directions ─────────────────────────────────────────────

DIRECTIONS: Dict[str, Direction] = {

    # ── GCP → AWS ──────────────────────────────────────────────────────
    "gcp-aws": Direction(
        key="gcp-aws",
        source_cloud="GCP",
        target_cloud="AWS",
        source_provider="google",
        target_provider="aws",
        source_label="Google Cloud Platform",
        target_label="Amazon Web Services",
        output_suffix="_aws",
        standard_vars=["aws_region", "aws_account_id", "project_name", "environment"],
    ),

    # ── AWS → GCP ──────────────────────────────────────────────────────
    "aws-gcp": Direction(
        key="aws-gcp",
        source_cloud="AWS",
        target_cloud="GCP",
        source_provider="aws",
        target_provider="google",
        source_label="Amazon Web Services",
        target_label="Google Cloud Platform",
        output_suffix="_gcp",
        standard_vars=["gcp_project_id", "gcp_region", "project_name", "environment"],
    ),

    # ── GCP → Azure ────────────────────────────────────────────────────
    "gcp-azure": Direction(
        key="gcp-azure",
        source_cloud="GCP",
        target_cloud="Azure",
        source_provider="google",
        target_provider="azurerm",
        source_label="Google Cloud Platform",
        target_label="Microsoft Azure",
        output_suffix="_azure",
        standard_vars=["azure_subscription_id", "azure_location", "project_name", "environment"],
    ),

    # ── Azure → GCP ────────────────────────────────────────────────────
    "azure-gcp": Direction(
        key="azure-gcp",
        source_cloud="Azure",
        target_cloud="GCP",
        source_provider="azurerm",
        target_provider="google",
        source_label="Microsoft Azure",
        target_label="Google Cloud Platform",
        output_suffix="_gcp",
        standard_vars=["gcp_project_id", "gcp_region", "project_name", "environment"],
    ),

    # ── Azure → AWS ────────────────────────────────────────────────────
    "azure-aws": Direction(
        key="azure-aws",
        source_cloud="Azure",
        target_cloud="AWS",
        source_provider="azurerm",
        target_provider="aws",
        source_label="Microsoft Azure",
        target_label="Amazon Web Services",
        output_suffix="_aws",
        standard_vars=["aws_region", "aws_account_id", "project_name", "environment"],
    ),

    # ── AWS → Azure ────────────────────────────────────────────────────
    "aws-azure": Direction(
        key="aws-azure",
        source_cloud="AWS",
        target_cloud="Azure",
        source_provider="aws",
        target_provider="azurerm",
        source_label="Amazon Web Services",
        target_label="Microsoft Azure",
        output_suffix="_azure",
        standard_vars=["azure_subscription_id", "azure_location", "project_name", "environment"],
    ),
}


def get_direction(key: str) -> Direction:
    """Return a Direction by key; raise ValueError with helpful message on miss."""
    key = key.lower().strip()
    if key not in DIRECTIONS:
        valid = ", ".join(DIRECTIONS.keys())
        raise ValueError(f"Unknown direction '{key}'. Valid options: {valid}")
    return DIRECTIONS[key]


def all_direction_keys() -> List[str]:
    return list(DIRECTIONS.keys())


def parse_direction_from_clouds(source: str, target: str) -> Direction:
    """Resolve a Direction from free-form cloud names, e.g. ('gcp', 'aws')."""
    key = f"{source.lower()}-{target.lower()}"
    return get_direction(key)
