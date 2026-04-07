"""
LangGraph Pipeline
==================
  [START]
     │
     ▼
  scanner              ← discovers all IaC files, classifies roles, maps modules
     │
     ▼
  project_understanding ← LLM reads ENTIRE codebase, builds variable/output/wiring map
     │
     ▼
  converter            ← LLM converts each file USING the understanding map
     │                    (variables.tf, outputs.tf, root main.tf all handled correctly)
     ▼
  postprocessor        ← generates provider.tf, backend.tf
     │
     ▼
  writer               ← writes all files to disk
     │
     ▼
  reporter             ← final summary
     │
     ▼
  [END]
"""
from langgraph.graph import StateGraph, START, END

from src.graph.state import ConversionState
from src.agents.scanner import file_scanner_agent
from src.agents.project_understanding import project_understanding_agent
from src.agents.analyzer import analyzer_agent
from src.agents.converter import converter_agent
from src.agents.postprocessor import postprocessor_agent
from src.agents.writer import writer_agent
from src.agents.reporter import reporter_agent


def _after_scanner(state: ConversionState) -> str:
    if state.status == "failed" or not state.discovered_files:
        return "reporter"
    return "project_understanding"


def _after_understanding(state: ConversionState) -> str:
    if len(state.errors) > 5:
        return "reporter"
    return "converter"


def build_graph() -> StateGraph:
    graph = StateGraph(ConversionState)

    graph.add_node("scanner",               file_scanner_agent)
    graph.add_node("project_understanding", project_understanding_agent)
    graph.add_node("analyzer",              analyzer_agent)   # kept for report metadata
    graph.add_node("converter",             converter_agent)
    graph.add_node("postprocessor",         postprocessor_agent)
    graph.add_node("writer",                writer_agent)
    graph.add_node("reporter",              reporter_agent)

    graph.add_edge(START, "scanner")

    graph.add_conditional_edges(
        "scanner",
        _after_scanner,
        {"project_understanding": "project_understanding", "reporter": "reporter"},
    )

    graph.add_conditional_edges(
        "project_understanding",
        _after_understanding,
        {"converter": "converter", "reporter": "reporter"},
    )

    graph.add_edge("converter",     "postprocessor")
    graph.add_edge("postprocessor", "writer")
    graph.add_edge("writer",        "reporter")
    graph.add_edge("reporter",      END)

    return graph.compile()


pipeline = build_graph()
