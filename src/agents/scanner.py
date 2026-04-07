"""
Agent 1 – File Scanner
Module-structure-aware: detects modules/ directory, classifies each file
by its role (main, variables, outputs, provider, backend, other) and
which module it belongs to.
"""
import os
from pathlib import Path
from typing import List, Dict

from src.graph.state import ConversionState, FileInfo, ModuleInfo
from src.directions import get_direction

IaC_EXTENSIONS = {
    ".tf": "terraform",
    ".tfvars": "terraform_vars",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".hcl": "hcl",
    ".bicep": "bicep",
    ".bicepparam": "bicep",
}

SKIP_DIRS = {
    ".git", ".terraform", "node_modules", "__pycache__",
    ".tox", "venv", ".venv", "dist", "build",
}

RESOURCE_PREFIXES = {
    "google":  ["google_"],
    "aws":     ["aws_"],
    "azurerm": ["azurerm_"],
}

CLOUD_YAML_HINTS = {
    "google":  ["kind: Deployment", "gke", "cloud-run", "pubsub", "google.com"],
    "aws":     ["AWSTemplateFormatVersion", "Type: AWS::", "cloudformation", "aws_"],
    "azurerm": ["$schema", "Microsoft.", "azurerm", "azure-pipelines"],
}


def _detect_resources(content: str, file_type: str, source_provider: str) -> List[str]:
    found = []
    prefixes = RESOURCE_PREFIXES.get(source_provider, [])
    if file_type in ("terraform", "hcl"):
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("resource "):
                parts = stripped.split('"')
                if len(parts) >= 2:
                    rtype = parts[1]
                    if any(rtype.startswith(p) for p in prefixes):
                        found.append(rtype)
    elif file_type in ("yaml", "json", "bicep"):
        for hint in CLOUD_YAML_HINTS.get(source_provider, []):
            if hint.lower() in content.lower():
                found.append(hint)
    return list(set(found))


def _classify_file_role(filename: str, content: str) -> str:
    """Determine the role of a Terraform file by name and content."""
    stem = Path(filename).stem.lower()
    if stem in ("variables", "vars"):
        return "variables"
    if stem in ("output", "outputs"):
        return "outputs"
    if stem in ("provider", "providers", "versions"):
        return "provider"
    if stem == "backend":
        return "backend"
    if stem == "main":
        return "main"
    # Fallback: inspect content
    if "variable " in content and "resource " not in content:
        return "variables"
    if "output " in content and "resource " not in content:
        return "outputs"
    if 'provider "' in content or "required_providers" in content:
        return "provider"
    return "resource"


def _get_module_name(relative_path: str, source_dir: Path) -> str:
    """
    Extract the module name from a file's relative path.
    e.g. modules/networking/main.tf  -> 'networking'
         modules/compute/variables.tf -> 'compute'
         terraform/main.tf            -> 'root'
         main.tf                      -> 'root'
    """
    parts = Path(relative_path).parts
    if len(parts) == 1:
        return "root"
    if parts[0] == "modules" and len(parts) >= 3:
        return parts[1]
    # terraform/ or any other top-level folder = root
    return "root"


def file_scanner_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: scan source directory with full module awareness."""
    source_dir = Path(state.source_dir).resolve()

    if not source_dir.exists():
        state.errors.append(f"Source directory does not exist: {source_dir}")
        state.status = "failed"
        return state

    direction = get_direction(state.direction)
    source_provider = direction.source_provider

    # Detect if this is a module-based project
    modules_dir = source_dir / "modules"
    is_module_project = modules_dir.exists() and modules_dir.is_dir()
    state.is_module_project = is_module_project

    discovered: List[FileInfo] = []
    skipped: List[str] = []
    modules: Dict[str, ModuleInfo] = {}

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
            file_role = _classify_file_role(filename, content)
            module_name = _get_module_name(relative, source_dir)

            # Build module registry
            if module_name not in modules:
                module_path = str(filepath.parent.relative_to(source_dir))
                modules[module_name] = ModuleInfo(
                    name=module_name,
                    path=module_path,
                )
            mod = modules[module_name]
            mod.files.append(relative)
            mod.resource_types.extend(resources)
            if file_role == "variables":
                mod.has_variables = True
            if file_role == "outputs":
                mod.has_outputs = True
            if file_role in ("main", "resource"):
                mod.has_main = True

            discovered.append(FileInfo(
                path=str(filepath),
                relative_path=relative,
                content=content,
                file_type=file_type,
                resource_types=resources,
                file_role=file_role,
                module_name=module_name,
            ))

    state.discovered_files = discovered
    state.total_files = len(discovered)
    state.skipped_files = skipped
    state.modules = modules

    if not discovered:
        state.warnings.append(
            f"No IaC files found. Expected {direction.source_label} "
            f"Terraform/IaC files (.tf, .yaml, .json, .hcl, .bicep)."
        )

    if is_module_project:
        state.warnings.append(
            f"Module-based project detected. Found modules: "
            f"{', '.join(k for k in modules if k != 'root')}"
        )

    return state