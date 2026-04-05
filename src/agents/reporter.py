"""
Agent 6 – Reporter
Produces a human-readable conversion report and sets final status.
Pure Python – no LLM call needed.
"""
from src.graph.state import ConversionState


def reporter_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: finalise state and generate the conversion report.
    """
    converted = len(state.converted_files)
    failed = len(state.failed_files)
    total = state.total_files

    # Tally all AWS resource types
    aws_resources: dict[str, int] = {}
    for cf in state.converted_files:
        for r in cf.resources_converted:
            aws_resources[r] = aws_resources.get(r, 0) + 1

    # Determine overall status
    if failed == 0 and converted > 0:
        state.status = "completed"
    elif converted > 0 and failed > 0:
        state.status = "completed_with_errors"
    elif converted == 0 and failed == 0:
        state.status = "no_files"
    else:
        state.status = "failed"

    lines = [
        "=" * 60,
        "  GCP → AWS TERRAFORM CONVERSION REPORT",
        "=" * 60,
        "",
        f"  Source directory : {state.source_dir}",
        f"  Output directory : {state.output_dir}",
        f"  LLM provider     : {state.provider}",
        f"  LLM model        : {state.model or '(default)'}",
        "",
        "─" * 60,
        "  FILE STATISTICS",
        "─" * 60,
        f"  Total IaC files discovered : {total}",
        f"  Successfully converted     : {converted}",
        f"  Failed                     : {failed}",
        f"  Skipped (non-IaC)          : {len(state.skipped_files)}",
        "",
    ]

    if aws_resources:
        lines += [
            "─" * 60,
            "  AWS RESOURCES GENERATED",
            "─" * 60,
        ]
        for res, count in sorted(aws_resources.items()):
            lines.append(f"  {res:<50} x{count}")
        lines.append("")

    if state.warnings:
        lines += ["─" * 60, "  WARNINGS", "─" * 60]
        for w in state.warnings:
            lines.append(f"  ⚠  {w}")
        lines.append("")

    if state.errors:
        lines += ["─" * 60, "  ERRORS", "─" * 60]
        for e in state.errors:
            lines.append(f"  ✗  {e}")
        lines.append("")

    if state.failed_files:
        lines += ["─" * 60, "  FAILED FILES", "─" * 60]
        for f in state.failed_files:
            lines.append(f"  ✗  {f}")
        lines.append("")

    lines += [
        "─" * 60,
        f"  STATUS: {state.status.upper()}",
        "=" * 60,
    ]

    state.conversion_report = "\n".join(lines)
    return state
