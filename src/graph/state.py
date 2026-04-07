"""
Graph state shared across all LangGraph nodes.
Now direction-aware and module-structure-aware.
"""
from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field
import operator


class FileInfo(BaseModel):
    """Represents a single source file discovered during scanning."""
    path: str
    relative_path: str
    content: str
    file_type: str
    resource_types: List[str] = Field(default_factory=list)
    # NEW: role this file plays in the project structure
    file_role: str = "resource"   # resource | variables | outputs | main | provider | backend | other
    module_name: str = ""         # e.g. "networking", "compute", "" for root


class ConvertedFile(BaseModel):
    """Represents a successfully converted or generated IaC file."""
    source_path: str              # empty string for newly generated files
    output_path: str
    aws_content: str              # holds target IaC content (name kept for compat)
    resources_converted: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: str = ""
    is_generated: bool = False    # True = new file with no source equivalent


class ModuleInfo(BaseModel):
    """Tracks a discovered Terraform module and all its files."""
    name: str                     # e.g. "networking", "compute", "root"
    path: str                     # directory path
    files: List[str] = Field(default_factory=list)   # relative paths of files in module
    resource_types: List[str] = Field(default_factory=list)
    has_variables: bool = False
    has_outputs: bool = False
    has_main: bool = False


class ConversionState(BaseModel):
    """Shared state flowing through every LangGraph node."""

    # ── Input ──────────────────────────────────────────────────────────
    source_dir: str = ""
    output_dir: str = ""
    direction: str = "gcp-aws"

    # LLM config
    provider: str = "openai"
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    # ── Discovery ──────────────────────────────────────────────────────
    discovered_files: List[FileInfo] = Field(default_factory=list)
    total_files: int = 0
    skipped_files: List[str] = Field(default_factory=list)
    # NEW: discovered module structure
    modules: Dict[str, ModuleInfo] = Field(default_factory=dict)
    is_module_project: bool = False   # True when modules/ directory found

    # ── Analysis ───────────────────────────────────────────────────────
    gcp_resource_summary: Dict[str, Any] = Field(default_factory=dict)
    resource_dependency_map: Dict[str, List[str]] = Field(default_factory=dict)
    conversion_plan: str = ""

    # ── Conversion ─────────────────────────────────────────────────────
    converted_files: Annotated[List[ConvertedFile], operator.add] = Field(
        default_factory=list
    )
    failed_files: Annotated[List[str], operator.add] = Field(default_factory=list)

    # ── Post-processing ────────────────────────────────────────────────
    variables_tf: str = ""
    outputs_tf: str = ""
    provider_tf: str = ""
    backend_tf: str = ""

    # ── Summary ────────────────────────────────────────────────────────
    conversion_report: str = ""
    errors: Annotated[List[str], operator.add] = Field(default_factory=list)
    warnings: Annotated[List[str], operator.add] = Field(default_factory=list)
    status: str = "pending"

    class Config:
        arbitrary_types_allowed = True