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

`stream_pipeline()` is the primary entry point: it runs the graph via
LangGraph's own `.stream()` (not `.invoke()`) so callers get a human-
readable log line after every node, not just the final result -- both
main.py (CLI) and server.py (API) use it so nobody is ever staring at a
silent "running" state with no way to tell what the agent is actually
doing. `run_pipeline()` is a thin wrapper for callers that just want the
final CompanyIntel.
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
    # Keep the exact text the LLM saw attached to the result -- proof every
    # field can be checked against, not just the model's word for it.
    intel.source_text = state.get("combined_text", "")

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


# --- Live progress reporting ---------------------------------------------
#
# Turns each node's raw output into a human-readable line, so both the CLI
# and the web app can show what the agent is actually doing step by step
# instead of a single opaque "running..." state -- this is also where a
# viewer can see the Critique Agent's verification work happen, not just
# its final verdict.

def _describe_step(node_name: str, output: dict) -> str:
    if node_name == "scrape":
        n = len(output.get("pages") or {})
        if n == 0:
            errs = "; ".join(output.get("scrape_errors") or [])
            return f"Scraper: no pages could be fetched ({errs or 'no reachable pages'})"
        extra = f" + {n - 1} subpage(s)" if n > 1 else ""
        return f"Scraper: fetched homepage{extra} ({n} page(s) total)"

    if node_name == "process":
        chars = len(output.get("combined_text") or "")
        return f"Processor: cleaned scraped HTML down to {chars:,} characters of text for the LLM"

    if node_name == "extract":
        err = output.get("extraction_error")
        call_n = output.get("llm_calls_used", "?")
        if err:
            return f"Extractor: LLM call #{call_n} failed -- {err}"
        return f"Extractor: LLM call #{call_n} returned structured data"

    if node_name == "critique":
        notes = output.get("critique_notes") or []
        n_emails = len(output.get("cleaned_emails") or [])
        n_leads = len(output.get("cleaned_leadership") or [])
        if output.get("needs_retry"):
            return "Critique: result unusable (no overview or ICP) -- requesting one retry"
        if notes:
            return f"Critique: flagged {len(notes)} unverifiable item(s) and dropped them -- {n_emails} email(s), {n_leads} leader(s) confirmed against source"
        return f"Critique: verified {n_emails} email(s) and {n_leads} leader(s) against the scraped source -- nothing dropped"

    if node_name == "retry":
        return "Retrying extraction with corrective feedback from Critique"

    if node_name == "finalize":
        result: Optional[CompanyIntel] = output.get("result")
        if result is None:
            return "Finalize: no result produced"
        return f"Finalize: status={result.status}, confidence={result.confidence_score:.2f}"

    return f"{node_name}: complete"


def stream_pipeline(domain: str):
    """Runs the graph for one domain, yielding a log line after every node
    completes, and finally the CompanyIntel result. Both the CLI (main.py)
    and the API (server.py) consume this -- it's the single source of
    "what actually happened" for a run.

    Yields dicts: {"type": "log", "message": str} for each step, then
    {"type": "result", "result": CompanyIntel} once.
    """
    graph = get_compiled_graph()
    initial_state = {"domain": domain, "llm_calls_used": 0, "retried": False}

    yield {"type": "log", "message": f"Starting pipeline for {domain}"}

    result: Optional[CompanyIntel] = None
    for step in graph.stream(initial_state, stream_mode="updates"):
        for node_name, output in step.items():
            yield {"type": "log", "message": _describe_step(node_name, output)}
            if node_name == "finalize":
                result = output.get("result")

    yield {"type": "result", "result": result}


def run_pipeline(domain: str) -> CompanyIntel:
    """Run the full graph for one domain and return its final CompanyIntel.
    Convenience wrapper around stream_pipeline() for callers that don't
    need the intermediate log lines (e.g. quick scripts)."""
    result = None
    for event in stream_pipeline(domain):
        if event["type"] == "result":
            result = event["result"]
    return result
