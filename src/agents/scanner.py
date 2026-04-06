"""
Agent 1 – File Scanner
Walks source directory recursively. Direction-aware: detects
the correct source cloud's resource types based on state.direction.
"""
import os
from pathlib import Path
from typing import List

from src.graph.state import ConversionState, FileInfo
from src.directions import get_direction

IaC_EXTENSIONS = {
    ".tf": "terraform",
    ".tfvars": "terraform_vars",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".hcl": "hcl",
    ".bicep": "bicep",       # Azure Bicep files
    ".bicepparam": "bicep",
}

SKIP_DIRS = {
    ".git", ".terraform", "node_modules", "__pycache__",
    ".tox", "venv", ".venv", "dist", "build",
}

# Resource prefixes per source cloud provider
RESOURCE_PREFIXES = {
    "google":  ["google_"],
    "aws":     ["aws_", "data.aws_"],
    "azurerm": ["azurerm_", "resource \"azurerm_"],
}

# YAML/JSON keyword hints per source cloud
CLOUD_YAML_HINTS = {
    "google":  ["kind: Deployment", "gke", "cloud-run", "pubsub", "google.com"],
    "aws":     ["AWSTemplateFormatVersion", "Type: AWS::", "cloudformation", "aws_"],
    "azurerm": ["$schema", "Microsoft.", "azurerm", "azure-pipelines"],
}


def _detect_resources(content: str, file_type: str, source_provider: str) -> List[str]:
    """Detect source-cloud resource types in a file."""
    found = []
    prefixes = RESOURCE_PREFIXES.get(source_provider, [])

    if file_type in ("terraform", "hcl"):
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("resource "):
                parts = stripped.split('"')
                if len(parts) >= 2:
                    rtype = parts[1]
                    if any(rtype.startswith(p.strip('"')) for p in prefixes):
                        found.append(rtype)
    elif file_type in ("yaml", "json", "bicep"):
        hints = CLOUD_YAML_HINTS.get(source_provider, [])
        for hint in hints:
            if hint.lower() in content.lower():
                found.append(hint)

    return list(set(found))


def file_scanner_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: scan source directory and populate discovered_files."""
    source_dir = Path(state.source_dir).resolve()

    if not source_dir.exists():
        state.errors.append(f"Source directory does not exist: {source_dir}")
        state.status = "failed"
        return state

    direction = get_direction(state.direction)
    source_provider = direction.source_provider

    discovered: List[FileInfo] = []
    skipped: List[str] = []

    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            filepath = Path(root) / filename
            ext = filepath.suffix.lower()

            if ext not in IaC_EXTENSIONS:
                skipped.append(str(filepath))
                continue

            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                skipped.append(f"{filepath} (read error: {exc})")
                continue

            file_type = IaC_EXTENSIONS[ext]
            resources = _detect_resources(content, file_type, source_provider)
            relative = str(filepath.relative_to(source_dir))

            discovered.append(FileInfo(
                path=str(filepath),
                relative_path=relative,
                content=content,
                file_type=file_type,
                resource_types=resources,
            ))

    state.discovered_files = discovered
    state.total_files = len(discovered)
    state.skipped_files = skipped

    if not discovered:
        state.warnings.append(
            f"No IaC files found. Expected {direction.source_label} "
            f"Terraform/IaC files (.tf, .yaml, .json, .hcl, .bicep)."
        )

    return state
