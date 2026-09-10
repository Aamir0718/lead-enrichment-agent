"""LangGraph orchestration.

Wires the four pipeline agents (Scraper, Processor, Extractor, Critique)
into a LangGraph StateGraph. This replaces the hand-rolled if/else control
flow that used to live in main.py with explicit nodes and conditional
edges -- same architecture, same LLM-call budget (1 call typical, 2 worst
case per domain), just orchestrated as a real graph instead of a linear
script.

Graph shape:

    scrape --(pages found?)--> process --> extract --(parsed ok?)--> critique
      |no pages                                |no                     |
      v                                        v                       v
   finalize <----------------------------- finalize          (needs retry?)
                                                              /            \
                                                          yes/              \no
                                                            v                v
                                                          retry -> extract  finalize

`retry` is only ever taken once: the Critique Agent's own node marks the
state as already-retried before requesting a second pass, so a second
"needs_retry" can never fire.
"""
from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.critique import critique
from agents.extractor import extract
from agents.processor import process_pages
from agents.scraper import scrape_domain
from models import CompanyIntel, ExtractionResult, TeamMember


class PipelineState(TypedDict, total=False):
    domain: str
    pages: dict
    pages_scraped: list
    scrape_errors: list

    combined_text: str

    extraction: Optional[ExtractionResult]
    extraction_error: Optional[str]
    llm_calls_used: int

    retried: bool
    retry_feedback: Optional[str]
    needs_retry: bool

    cleaned_emails: list
    cleaned_leadership: list
    confidence_score: float
    critique_notes: list

    result: CompanyIntel


# --- Nodes ------------------------------------------------------------

def scrape_node(state: PipelineState) -> dict:
    """Scraper Agent (deterministic)."""
    result = scrape_domain(state["domain"])
    return {
        "pages": result.pages,
        "pages_scraped": list(result.pages.keys()),
        "scrape_errors": result.errors,
    }


def process_node(state: PipelineState) -> dict:
    """Processor Agent (deterministic)."""
    processed = process_pages(state["pages"])
    return {"combined_text": processed.combined_text}


def extract_node(state: PipelineState) -> dict:
    """Extractor Agent -- the only node that calls an LLM."""
    result, err = extract(
        state["domain"],
        state["combined_text"],
        feedback=state.get("retry_feedback"),
    )
    return {
        "extraction": result,
        "extraction_error": err,
        "llm_calls_used": state.get("llm_calls_used", 0) + 1,
    }


def critique_node(state: PipelineState) -> dict:
    """Critique Agent (deterministic unless it requests a retry)."""
    outcome = critique(state["extraction"], state["combined_text"])
    already_retried = state.get("retried", False)
    return {
        "cleaned_emails": outcome.cleaned_emails,
        "cleaned_leadership": outcome.cleaned_leadership,
        "confidence_score": outcome.confidence_score,
        "critique_notes": outcome.notes,
        "needs_retry": outcome.needs_retry and not already_retried,
        "retry_feedback": outcome.retry_feedback,
    }


def retry_node(state: PipelineState) -> dict:
    """Marks the retry budget as spent, then loops back to Extract."""
    return {"retried": True}


def finalize_node(state: PipelineState) -> dict:
    """Main Agent's aggregation step -- builds the final CompanyIntel."""
    intel = CompanyIntel(domain=state["domain"], pages_scraped=state.get("pages_scraped", []))
    intel.llm_calls_used = state.get("llm_calls_used", 0)

    if not state.get("pages"):
        intel.status = "failed"
        intel.error = "; ".join(state.get("scrape_errors", [])) or "No pages could be fetched"
        return {"result": intel}

    extraction = state.get("extraction")
    if extraction is None:
        intel.status = "failed"
        intel.error = state.get("extraction_error")
        return {"result": intel}

    intel.company_overview = extraction.company_overview
    intel.target_audience = extraction.target_audience
    intel.contact_emails = state.get("cleaned_emails", [])
    intel.leadership = state.get("cleaned_leadership", [])
    intel.confidence_score = state.get("confidence_score", 0.0)
    intel.critique_notes = state.get("critique_notes", [])

    has_overview = bool(intel.company_overview and intel.company_overview.strip())
    has_audience = bool(intel.target_audience and intel.target_audience.strip())
    if has_overview and has_audience:
        intel.status = "success"
    elif has_overview or has_audience:
        intel.status = "partial"
    else:
        intel.status = "failed"
        intel.error = intel.error or "Usable overview/ICP could not be extracted after retry"

    return {"result": intel}


# --- Conditional routing ------------------------------------------------

def route_after_scrape(state: PipelineState) -> str:
    return "process" if state.get("pages") else "finalize"


def route_after_extract(state: PipelineState) -> str:
    return "critique" if state.get("extraction") is not None else "finalize"


def route_after_critique(state: PipelineState) -> str:
    return "retry" if state.get("needs_retry") else "finalize"


# --- Graph assembly -------------------------------------------------------

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("scrape", scrape_node)
    graph.add_node("process", process_node)
    graph.add_node("extract", extract_node)
    graph.add_node("critique", critique_node)
    graph.add_node("retry", retry_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("scrape")
    graph.add_conditional_edges("scrape", route_after_scrape, {"process": "process", "finalize": "finalize"})
    graph.add_edge("process", "extract")
    graph.add_conditional_edges("extract", route_after_extract, {"critique": "critique", "finalize": "finalize"})
    graph.add_conditional_edges("critique", route_after_critique, {"retry": "retry", "finalize": "finalize"})
    graph.add_edge("retry", "extract")
    graph.add_edge("finalize", END)

    return graph.compile()


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_pipeline(domain: str) -> CompanyIntel:
    """Run the full graph for one domain and return its final CompanyIntel."""
    graph = get_compiled_graph()
    final_state = graph.invoke({"domain": domain, "llm_calls_used": 0, "retried": False})
    return final_state["result"]
