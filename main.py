#!/usr/bin/env python3
"""
Cloud IaC Converter — Multi-Cloud Terraform Migration Tool
Powered by LangGraph + Your LLM of Choice

Supported directions:
  gcp-aws    GCP  → AWS
  aws-gcp    AWS  → GCP
  gcp-azure  GCP  → Azure
  azure-gcp  Azure → GCP
  azure-aws  Azure → AWS
  aws-azure  AWS  → Azure

Usage:
  python main.py convert --source ./gcp-infra --output ./aws-out --direction gcp-aws --provider openai
  python main.py convert --source ./aws-infra --output ./gcp-out --direction aws-gcp --provider anthropic
  python main.py convert --source ./azure    --output ./aws-out  --direction azure-aws --provider ollama --model codellama:13b
  python main.py directions
  python main.py scan --source ./infra --direction gcp-aws
"""
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich import box

load_dotenv()

console = Console()

BANNER = """
[bold cyan]╔══════════════════════════════════════════════════════════╗
║     Cloud IaC Converter  ·  Multi-Cloud Terraform Tool   ║
║     Powered by LangGraph + Your LLM of Choice            ║
╚══════════════════════════════════════════════════════════╝[/bold cyan]
"""

SUPPORTED_PROVIDERS = {
    "openai":    ("OPENAI_API_KEY",       "gpt-4o"),
    "anthropic": ("ANTHROPIC_API_KEY",    "claude-3-5-sonnet-20241022"),
    "google":    ("GOOGLE_API_KEY",       "gemini-1.5-pro"),
    "groq":      ("GROQ_API_KEY",         "llama3-70b-8192"),
    "ollama":    (None,                    "codellama:13b"),
    "azure":     ("AZURE_OPENAI_API_KEY", "gpt-4o"),
}

NO_KEY_PROVIDERS = {"ollama"}


def _resolve_api_key(provider: str, api_key) -> str:
    if api_key:
        return api_key
    env_var, _ = SUPPORTED_PROVIDERS.get(provider, (None, None))
    if env_var:
        return os.getenv(env_var, "")
    return ""


@click.group()
def cli():
    """Multi-cloud IaC converter — converts Terraform between AWS, GCP, and Azure."""
    pass


# ── directions command ─────────────────────────────────────────────────────

@cli.command()
def directions():
    """List all supported conversion directions."""
    console.print(BANNER)

    from src.directions import DIRECTIONS

    table = Table(title="Supported Conversion Directions", box=box.ROUNDED, border_style="cyan")
    table.add_column("Direction",    style="bold yellow", width=12)
    table.add_column("From",         style="white")
    table.add_column("To",           style="green")
    table.add_column("File suffix",  style="dim")

    for key, d in DIRECTIONS.items():
        table.add_row(key, d.source_label, d.target_label, d.output_suffix + ".tf")

    console.print(table)
    console.print()

    ptable = Table(title="Supported LLM Providers", box=box.ROUNDED, border_style="cyan")
    ptable.add_column("Provider", style="bold yellow")
    ptable.add_column("Default Model", style="green")
    ptable.add_column("Env Var", style="dim")
    for p, (env, model) in SUPPORTED_PROVIDERS.items():
        ptable.add_row(p, model, env or "N/A (local)")
    console.print(ptable)


# ── scan command ───────────────────────────────────────────────────────────

@cli.command()
@click.option("--source",    "-s", required=True, help="Path to source IaC directory.")
@click.option("--direction", "-d", required=True,
              type=click.Choice(["gcp-aws","aws-gcp","gcp-azure","azure-gcp","azure-aws","aws-azure"],
                                case_sensitive=False),
              help="Conversion direction.")
def scan(source, direction):
    """Dry-run: scan a directory and list all IaC files found (no LLM calls)."""
    console.print(BANNER)

    from src.graph.state import ConversionState
    from src.agents.scanner import file_scanner_agent
    from src.directions import get_direction

    d = get_direction(direction)
    state = ConversionState(source_dir=source, output_dir="/tmp/dry-run", direction=direction)
    result = file_scanner_agent(state)

    table = Table(
        title=f"IaC Files in {source} ({d.source_label})",
        box=box.ROUNDED, border_style="cyan"
    )
    table.add_column("File", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Resources found", style="green")

    for f in result.discovered_files:
        table.add_row(
            f.relative_path,
            f.file_type,
            ", ".join(f.resource_types) or "—",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {result.total_files} | Skipped: {len(result.skipped_files)}[/]")


# ── convert command ────────────────────────────────────────────────────────

@cli.command()
@click.option("--source",    "-s", required=True, help="Path to source IaC directory.")
@click.option("--output",    "-o", required=True, help="Path to write converted Terraform.")
@click.option("--direction", "-d", required=True,
              type=click.Choice(["gcp-aws","aws-gcp","gcp-azure","azure-gcp","azure-aws","aws-azure"],
                                case_sensitive=False),
              help="Conversion direction, e.g. gcp-aws or aws-azure.")
@click.option("--provider",  "-p", default="openai",
              type=click.Choice(list(SUPPORTED_PROVIDERS.keys()), case_sensitive=False),
              show_default=True, help="LLM provider.")
@click.option("--model",     "-m", default=None,  help="Model override.")
@click.option("--api-key",   "-k", default=None,  help="API key (falls back to env var).")
@click.option("--verbose",   "-v", is_flag=True,  help="Print each converted file path.")
def convert(source, output, direction, provider, model, api_key, verbose):
    """Convert a cloud IaC codebase from one cloud to another."""
    console.print(BANNER)

    from src.graph.state import ConversionState
    from src.graph.pipeline import pipeline
    from src.directions import get_direction

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    d = get_direction(direction)

    if not source_path.exists():
        console.print(f"[bold red]✗ Source directory not found:[/] {source_path}")
        sys.exit(1)

    resolved_key = _resolve_api_key(provider, api_key)
    if provider not in NO_KEY_PROVIDERS and not resolved_key:
        env_var = SUPPORTED_PROVIDERS[provider][0]
        console.print(
            f"[bold red]✗ No API key for '{provider}'.[/] "
            f"Set [yellow]{env_var}[/] or pass --api-key."
        )
        sys.exit(1)

    effective_model = model or SUPPORTED_PROVIDERS[provider][1]

    # Config summary
    summary = Table.grid(padding=(0, 2))
    summary.add_row("[dim]Direction:[/]", f"[bold cyan]{d.source_label}  →  {d.target_label}[/]")
    summary.add_row("[dim]Source:[/]",    f"[white]{source_path}[/]")
    summary.add_row("[dim]Output:[/]",    f"[white]{output_path}[/]")
    summary.add_row("[dim]Provider:[/]",  f"[bold yellow]{provider}[/]")
    summary.add_row("[dim]Model:[/]",     f"[bold green]{effective_model}[/]")
    console.print(Panel(summary, title="Configuration", border_style="cyan"))

    initial_state = ConversionState(
        source_dir=str(source_path),
        output_dir=str(output_path),
        direction=direction,
        provider=provider,
        model=effective_model,
        api_key=resolved_key or None,
        status="running",
    )

    step_map = {
        "scanner":       f"🔍  Scanning {d.source_label} source files…",
        "analyzer":      f"🧠  Analysing {d.source_cloud} infrastructure…",
        "converter":     f"⚙️   Converting {d.source_cloud} → {d.target_cloud} Terraform…",
        "postprocessor": f"📦  Generating {d.target_cloud} provider/variables/outputs…",
        "writer":        "💾  Writing output files…",
        "reporter":      "📋  Building conversion report…",
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]Starting pipeline…", total=None)

        for event in pipeline.stream(initial_state):
            for node_name in event:
                desc = step_map.get(node_name, f"Running {node_name}…")
                progress.update(task, description=f"[cyan]{desc}")

    # Get final typed state
    raw_result = pipeline.invoke(initial_state)
    if isinstance(raw_result, dict):
        final_state = ConversionState(**raw_result)
    else:
        final_state = raw_result

    # Print report
    console.print()
    report = final_state.conversion_report or "No report generated."
    status = final_state.status or "unknown"
    console.print(Panel(
        report,
        title=f"{d.source_cloud} → {d.target_cloud} Conversion Report",
        border_style="green" if "failed" not in status else "red",
        expand=False,
    ))

    if verbose and final_state.converted_files:
        console.print("\n[bold]Converted files:[/]")
        for cf in final_state.converted_files:
            console.print(f"  [green]✓[/] {cf.source_path}  →  [cyan]{cf.output_path}[/]")

    console.print(f"\n[bold green]✓ Output written to:[/] {output_path}\n")


if __name__ == "__main__":
    cli()
