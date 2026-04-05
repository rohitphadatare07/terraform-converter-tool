#!/usr/bin/env python3
"""
GCP → AWS Terraform Converter CLI
A LangGraph-powered agentic application.

Usage:
  python main.py convert \\
    --source ./my-gcp-infra \\
    --output ./aws-terraform \\
    --provider openai \\
    --model gpt-4o \\
    --api-key sk-...

  python main.py convert \\
    --source ./my-gcp-infra \\
    --output ./aws-terraform \\
    --provider anthropic

  python main.py convert \\
    --source ./my-gcp-infra \\
    --output ./aws-terraform \\
    --provider ollama \\
    --model codellama:13b
"""
import os
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

load_dotenv()

console = Console()

BANNER = """
[bold cyan]╔═══════════════════════════════════════════════════╗
║     GCP → AWS Terraform Converter                 ║
║     Powered by LangGraph + Your LLM of Choice    ║
╚═══════════════════════════════════════════════════╝[/bold cyan]
"""

SUPPORTED_PROVIDERS = {
    "openai":    ("OPENAI_API_KEY",          "gpt-4o"),
    "anthropic": ("ANTHROPIC_API_KEY",       "claude-3-5-sonnet-20241022"),
    "google":    ("GOOGLE_API_KEY",          "gemini-1.5-pro"),
    "groq":      ("GROQ_API_KEY",            "llama3-70b-8192"),
    "ollama":    (None,                       "codellama:13b"),
    "azure":     ("AZURE_OPENAI_API_KEY",    "gpt-4o"),
}


def _resolve_api_key(provider: str, api_key: str | None) -> str | None:
    if api_key:
        return api_key
    env_var, _ = SUPPORTED_PROVIDERS.get(provider, (None, None))
    if env_var:
        return os.getenv(env_var)
    return None


def _print_providers_table():
    table = Table(title="Supported LLM Providers", box=box.ROUNDED, border_style="cyan")
    table.add_column("Provider", style="bold yellow")
    table.add_column("Default Model", style="green")
    table.add_column("Env Var", style="dim")

    for p, (env, model) in SUPPORTED_PROVIDERS.items():
        table.add_row(p, model, env or "N/A (local)")

    console.print(table)


@click.group()
def cli():
    """GCP Infrastructure-as-Code → AWS Terraform converter using LangGraph."""
    pass


@cli.command()
def providers():
    """List all supported LLM providers."""
    console.print(BANNER)
    _print_providers_table()


@cli.command()
@click.option("--source",   "-s", required=True,  help="Path to GCP IaC source directory.")
@click.option("--output",   "-o", required=True,  help="Path to write AWS Terraform output.")
@click.option("--provider", "-p", default="openai",
              type=click.Choice(list(SUPPORTED_PROVIDERS.keys()), case_sensitive=False),
              show_default=True, help="LLM provider to use.")
@click.option("--model",    "-m", default=None,   help="Model override (uses provider default if omitted).")
@click.option("--api-key",  "-k", default=None,   help="API key (falls back to environment variable).")
@click.option("--verbose",  "-v", is_flag=True,   help="Print detailed progress.")
def convert(source, output, provider, model, api_key, verbose):
    """Convert a GCP IaC codebase to AWS Terraform."""
    console.print(BANNER)

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()

    # Validate source
    if not source_path.exists():
        console.print(f"[bold red]✗ Source directory not found:[/] {source_path}")
        sys.exit(1)

    resolved_key = _resolve_api_key(provider, api_key)
    if provider != "ollama" and not resolved_key:
        env_var = SUPPORTED_PROVIDERS[provider][0]
        console.print(
            f"[bold red]✗ No API key found for provider '{provider}'.[/] "
            f"Set [yellow]{env_var}[/] in environment or use --api-key."
        )
        sys.exit(1)

    default_model = SUPPORTED_PROVIDERS[provider][1]
    effective_model = model or default_model

    # Summary panel
    summary = Table.grid(padding=(0, 2))
    summary.add_row("[dim]Source:[/]",   f"[white]{source_path}[/]")
    summary.add_row("[dim]Output:[/]",   f"[white]{output_path}[/]")
    summary.add_row("[dim]Provider:[/]", f"[bold yellow]{provider}[/]")
    summary.add_row("[dim]Model:[/]",    f"[bold green]{effective_model}[/]")
    console.print(Panel(summary, title="Configuration", border_style="cyan"))

    # ── Import and run the LangGraph pipeline ──────────────────────────
    from src.graph.state import ConversionState
    from src.graph.pipeline import pipeline

    initial_state = ConversionState(
        source_dir=str(source_path),
        output_dir=str(output_path),
        provider=provider,
        model=effective_model,
        api_key=resolved_key,
        status="running",
    )

    steps = [
        ("scanner",       "🔍  Scanning source directory…"),
        ("analyzer",      "🧠  Analysing GCP infrastructure…"),
        ("converter",     "⚙️   Converting to AWS Terraform…"),
        ("postprocessor", "📦  Generating supporting files…"),
        ("writer",        "💾  Writing output files…"),
        ("reporter",      "📋  Building conversion report…"),
    ]

    final_state = None

    step_map = {node: desc for node, desc in steps}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]Starting pipeline…", total=None)

        # Stream for live progress updates only
        for event in pipeline.stream(initial_state):
            for node_name in event:
                desc = step_map.get(node_name, f"Running {node_name}…")
                progress.update(task, description=f"[cyan]{desc}")

    # invoke() returns the final typed ConversionState
    raw_result = pipeline.invoke(initial_state)
    if isinstance(raw_result, dict):
        final_state = ConversionState(**raw_result)
    else:
        final_state = raw_result


    # ── Print report ───────────────────────────────────────────────────
    if final_state:
        console.print()
        console.print(
            Panel(
                final_state.conversion_report,
                title="Conversion Report",
                border_style="green" if "failed" not in final_state.status else "red",
                expand=False,
            )
        )

        if verbose and final_state.converted_files:
            console.print("\n[bold]Converted files:[/]")
            for cf in final_state.converted_files:
                console.print(f"  [green]✓[/] {cf.source_path}  →  [cyan]{cf.output_path}[/]")

        console.print(
            f"\n[bold green]✓ Output written to:[/] {output_path}\n"
        )
    else:
        console.print("[bold red]Pipeline returned no state. Check errors above.[/]")
        sys.exit(1)


@cli.command()
@click.option("--source", "-s", required=True, help="Path to GCP IaC source directory.")
def scan(source):
    """Dry-run: scan a directory and list all IaC files found (no LLM calls)."""
    console.print(BANNER)

    from src.graph.state import ConversionState
    from src.agents.scanner import file_scanner_agent

    state = ConversionState(source_dir=source, output_dir="/tmp/dry-run")
    result = file_scanner_agent(state)

    table = Table(title=f"IaC Files in {source}", box=box.ROUNDED, border_style="cyan")
    table.add_column("File", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("GCP Resources", style="green")

    for f in result.discovered_files:
        table.add_row(
            f.relative_path,
            f.file_type,
            ", ".join(f.resource_types) or "—",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {result.total_files} files | Skipped: {len(result.skipped_files)}[/]")


if __name__ == "__main__":
    cli()