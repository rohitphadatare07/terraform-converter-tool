"""
Graph state shared across all LangGraph nodes.
Now direction-aware: works for any cloud-to-cloud conversion.
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


class ConvertedFile(BaseModel):
    """Represents a successfully converted IaC file."""
    source_path: str
    output_path: str
    aws_content: str        # kept as 'aws_content' for backward compat; holds target IaC
    resources_converted: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    notes: str = ""


class ConversionState(BaseModel):
    """
    Shared state flowing through every LangGraph node.
    All conversion directions use the same state shape.
    """

    # ── Input ──────────────────────────────────────────────────────────
    source_dir: str = ""
    output_dir: str = ""

    # Direction: one of gcp-aws, aws-gcp, gcp-azure, azure-gcp, azure-aws, aws-azure
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
