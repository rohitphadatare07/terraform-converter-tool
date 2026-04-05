"""
LangGraph Pipeline
Wires all agents into a directed acyclic graph (DAG):

  [START]
     │
     ▼
  scanner          ← discovers all IaC files (pure Python)
     │
     ▼
  analyzer         ← LLM: understands GCP resources, builds plan
     │
     ▼
  converter        ← LLM: converts each file to AWS Terraform
     │
     ▼
  postprocessor    ← LLM: generates provider/variables/outputs
     │
     ▼
  writer           ← writes all files to disk (pure Python)
     │
     ▼
  reporter         ← generates final report (pure Python)
     │
     ▼
  [END]
"""
from langgraph.graph import StateGraph, START, END

from src.graph.state import ConversionState
from src.agents.scanner import file_scanner_agent
from src.agents.analyzer import analyzer_agent
from src.agents.converter import converter_agent
from src.agents.postprocessor import postprocessor_agent
from src.agents.writer import writer_agent
from src.agents.reporter import reporter_agent


def _should_continue_after_scanner(state: ConversionState) -> str:
    """Conditional edge: abort early if scanner found nothing."""
    if state.status == "failed" or not state.discovered_files:
        return "reporter"
    return "analyzer"


def _should_continue_after_analyzer(state: ConversionState) -> str:
    """Conditional edge: abort if analyzer encountered a fatal error."""
    if len(state.errors) > 5:          # too many errors → bail out
        return "reporter"
    return "converter"


def build_graph() -> StateGraph:
    """Build and compile the LangGraph conversion pipeline."""
    graph = StateGraph(ConversionState)

    # ── Register nodes ─────────────────────────────────────────────────
    graph.add_node("scanner",       file_scanner_agent)
    graph.add_node("analyzer",      analyzer_agent)
    graph.add_node("converter",     converter_agent)
    graph.add_node("postprocessor", postprocessor_agent)
    graph.add_node("writer",        writer_agent)
    graph.add_node("reporter",      reporter_agent)

    # ── Edges ──────────────────────────────────────────────────────────
    graph.add_edge(START, "scanner")

    # After scanner: go to analyzer OR skip to reporter
    graph.add_conditional_edges(
        "scanner",
        _should_continue_after_scanner,
        {
            "analyzer": "analyzer",
            "reporter": "reporter",
        },
    )

    # After analyzer: go to converter OR skip to reporter
    graph.add_conditional_edges(
        "analyzer",
        _should_continue_after_analyzer,
        {
            "converter": "converter",
            "reporter": "reporter",
        },
    )

    graph.add_edge("converter",     "postprocessor")
    graph.add_edge("postprocessor", "writer")
    graph.add_edge("writer",        "reporter")
    graph.add_edge("reporter",      END)

    return graph.compile()


# Pre-compiled singleton (reuse across calls)
pipeline = build_graph()
