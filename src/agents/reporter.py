"""
Agent 6 – Reporter
Produces a human-readable conversion report. Direction-aware.
"""
from src.graph.state import ConversionState
from src.directions import get_direction


def reporter_agent(state: ConversionState) -> ConversionState:
    """LangGraph node: generate final conversion report and set status."""
    direction = get_direction(state.direction)
    converted = len(state.converted_files)
    failed = len(state.failed_files)

    aws_resources: dict[str, int] = {}
    for cf in state.converted_files:
        for r in cf.resources_converted:
            aws_resources[r] = aws_resources.get(r, 0) + 1

    if failed == 0 and converted > 0:
        state.status = "completed"
    elif converted > 0 and failed > 0:
        state.status = "completed_with_errors"
    elif converted == 0 and failed == 0:
        state.status = "no_files"
    else:
        state.status = "failed"

    lines = [
        "=" * 64,
        f"  {direction.source_cloud} → {direction.target_cloud} TERRAFORM CONVERSION REPORT",
        "=" * 64,
        "",
        f"  Direction        : {direction.source_label} → {direction.target_label}",
        f"  Source directory : {state.source_dir}",
        f"  Output directory : {state.output_dir}",
        f"  LLM provider     : {state.provider}",
        f"  LLM model        : {state.model or '(default)'}",
        "",
        "─" * 64,
        "  FILE STATISTICS",
        "─" * 64,
        f"  Total IaC files discovered : {state.total_files}",
        f"  Successfully converted     : {converted}",
        f"  Failed                     : {failed}",
        f"  Skipped (non-IaC)          : {len(state.skipped_files)}",
        "",
    ]

    if aws_resources:
        lines += ["─" * 64, "  TARGET RESOURCES GENERATED", "─" * 64]
        for res, count in sorted(aws_resources.items()):
            lines.append(f"  {res:<55} x{count}")
        lines.append("")

    if state.warnings:
        lines += ["─" * 64, "  WARNINGS", "─" * 64]
        for w in state.warnings:
            lines.append(f"  ⚠  {w}")
        lines.append("")

    if state.errors:
        lines += ["─" * 64, "  ERRORS", "─" * 64]
        for e in state.errors:
            lines.append(f"  ✗  {e}")
        lines.append("")

    if state.failed_files:
        lines += ["─" * 64, "  FAILED FILES", "─" * 64]
        for f in state.failed_files:
            lines.append(f"  ✗  {f}")
        lines.append("")

    lines += [
        "─" * 64,
        f"  STATUS: {state.status.upper()}",
        "=" * 64,
    ]

    state.conversion_report = "\n".join(lines)
    return state
