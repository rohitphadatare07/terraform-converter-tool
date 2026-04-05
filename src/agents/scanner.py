"""
Agent 1 – File Scanner
Walks the source directory recursively and reads all IaC files.
"""
import os
from pathlib import Path
from typing import List

from src.graph.state import ConversionState, FileInfo

# Extensions we care about
IaC_EXTENSIONS = {
    ".tf": "terraform",
    ".tfvars": "terraform_vars",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".hcl": "hcl",
}

# Folders to always skip
SKIP_DIRS = {
    ".git", ".terraform", "node_modules", "__pycache__",
    ".tox", "venv", ".venv", "dist", "build",
}

# GCP resource type prefixes we recognise in Terraform
GCP_RESOURCE_PREFIXES = [
    "google_compute_", "google_container_", "google_sql_",
    "google_storage_", "google_bigquery_", "google_pubsub_",
    "google_cloud_run_", "google_cloudfunctions_", "google_iam_",
    "google_project_", "google_dns_", "google_redis_",
    "google_spanner_", "google_filestore_", "google_dataflow_",
    "google_composer_", "google_dataproc_", "google_artifact_registry_",
    "google_secret_manager_", "google_kms_", "google_logging_",
    "google_monitoring_", "google_vpc_access_", "google_app_engine_",
    "google_", # catch-all
]

YAML_GCP_KEYWORDS = [
    "kind: Deployment", "kind: Service", "kind: Ingress",
    "gke", "cloud-run", "cloudfunctions", "pubsub",
    "cloudrun", "google.com",
]


def _detect_gcp_resources(content: str, file_type: str) -> List[str]:
    """Return a list of GCP resource type strings found in the content."""
    found = []
    if file_type in ("terraform", "hcl"):
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith('resource "google_'):
                # e.g. resource "google_compute_instance" "web"
                parts = stripped.split('"')
                if len(parts) >= 2:
                    found.append(parts[1])
    elif file_type in ("yaml", "json"):
        for kw in YAML_GCP_KEYWORDS:
            if kw.lower() in content.lower():
                found.append(kw)
    return list(set(found))


def file_scanner_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: scan the source directory and populate discovered_files.
    This node is pure Python – no LLM call needed.
    """
    source_dir = Path(state.source_dir).resolve()

    if not source_dir.exists():
        state.errors.append(f"Source directory does not exist: {source_dir}")
        state.status = "failed"
        return state

    discovered: List[FileInfo] = []
    skipped: List[str] = []

    for root, dirs, files in os.walk(source_dir):
        # Prune unwanted directories in-place
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
            resources = _detect_gcp_resources(content, file_type)
            relative = str(filepath.relative_to(source_dir))

            discovered.append(
                FileInfo(
                    path=str(filepath),
                    relative_path=relative,
                    content=content,
                    file_type=file_type,
                    resource_types=resources,
                )
            )

    state.discovered_files = discovered
    state.total_files = len(discovered)
    state.skipped_files = skipped

    if not discovered:
        state.warnings.append(
            "No IaC files found in the source directory. "
            "Make sure it contains .tf, .yaml, .yml, .json or .hcl files."
        )

    return state
