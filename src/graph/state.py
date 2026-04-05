"""
Graph state shared across all LangGraph nodes.
"""
from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field
import operator


class FileInfo(BaseModel):
    """Represents a single source file discovered during scanning."""
    path: str
    relative_path: str
    content: str
    file_type: str          # e.g. "terraform", "yaml", "json"
    resource_types: List[str] = Field(default_factory=list)  # GCP resource types found


class ConvertedFile(BaseModel):
    """Represents a successfully converted AWS Terraform file."""
    source_path: str
    output_path: str
    aws_content: str
    resources_converted: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: str = ""


class ConversionState(BaseModel):
    """
    The shared state that flows through every LangGraph node.

    Annotated fields with operator.add are automatically merged
    when multiple nodes update them in parallel branches.
    """

    # ── Input ──────────────────────────────────────────────────────────
    source_dir: str = ""                        # Root directory of GCP IaC
    output_dir: str = ""                        # Where to write AWS Terraform
    provider: str = "openai"                    # LLM provider
    model: Optional[str] = None                 # LLM model override
    api_key: Optional[str] = None              # LLM API key

    # ── Discovery phase ────────────────────────────────────────────────
    discovered_files: List[FileInfo] = Field(default_factory=list)
    total_files: int = 0
    skipped_files: List[str] = Field(default_factory=list)

    # ── Analysis phase ─────────────────────────────────────────────────
    gcp_resource_summary: Dict[str, Any] = Field(default_factory=dict)
    resource_dependency_map: Dict[str, List[str]] = Field(default_factory=dict)
    conversion_plan: str = ""

    # ── Conversion phase ───────────────────────────────────────────────
    # Annotated so parallel nodes can safely append to this list
    converted_files: Annotated[List[ConvertedFile], operator.add] = Field(
        default_factory=list
    )
    failed_files: Annotated[List[str], operator.add] = Field(default_factory=list)

    # ── Post-processing ────────────────────────────────────────────────
    variables_tf: str = ""          # Consolidated variables.tf
    outputs_tf: str = ""            # Consolidated outputs.tf
    provider_tf: str = ""           # AWS provider block
    backend_tf: str = ""            # Optional remote backend config

    # ── Summary ────────────────────────────────────────────────────────
    conversion_report: str = ""
    errors: Annotated[List[str], operator.add] = Field(default_factory=list)
    warnings: Annotated[List[str], operator.add] = Field(default_factory=list)
    status: str = "pending"         # pending | running | completed | failed

    class Config:
        arbitrary_types_allowed = True
