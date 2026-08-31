from langgraph.graph import StateGraph, END
from schemas import PipelineState
from agents import scanner_node, refactor_node, docs_node


def build_pipeline():
    """Builds the sequential Scanner -> Refactor -> Docs graph."""
    graph = StateGraph(PipelineState)

    graph.add_node("scanner", scanner_node)
    graph.add_node("refactor", refactor_node)
    graph.add_node("docs", docs_node)

    graph.set_entry_point("scanner")
    graph.add_edge("scanner", "refactor")
    graph.add_edge("refactor", "docs")
    graph.add_edge("docs", END)

    return graph.compile()


def initial_state(raw_code: str, language: str = "python", api_key: str = "") -> PipelineState:
    return {
        "raw_code": raw_code,
        "language": language,
        "api_key": api_key,
        "audit_report": None,
        "refactored_code": None,
        "changes_made": None,
        "issues_not_fixed": None,
        "readme_markdown": None,
        "docstring_annotated_code": None,
        "status_log": [],
        "current_step": "start",
        "error": None,
    }