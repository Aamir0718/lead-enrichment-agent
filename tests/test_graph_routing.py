"""Tests for graph.py's pure routing/aggregation functions -- built directly
against hand-crafted PipelineState dicts, no LangGraph runtime or mocking
needed since these are plain functions operating on dicts."""
from graph import (
    critique_node,
    finalize_node,
    route_after_critique,
    route_after_extract,
    route_after_scrape,
)
from models import ExtractionResult, TeamMember


class TestRouteAfterScrape:
    def test_routes_to_process_when_pages_found(self):
        assert route_after_scrape({"pages": {"https://acme.com": "<html></html>"}}) == "process"

    def test_routes_to_finalize_when_no_pages(self):
        assert route_after_scrape({"pages": {}}) == "finalize"
        assert route_after_scrape({}) == "finalize"


class TestRouteAfterExtract:
    def test_routes_to_critique_when_extraction_succeeded(self):
        fake_result = object()  # routing only checks for not-None, doesn't inspect it
        assert route_after_extract({"extraction": fake_result}) == "critique"

    def test_routes_to_retry_when_extraction_failed_and_budget_unused(self):
        # An outright call/parse failure (not a parsed-but-empty result)
        # gets the same one-time retry budget as Critique's own trigger.
        assert route_after_extract({"extraction": None}) == "retry"
        assert route_after_extract({}) == "retry"

    def test_routes_to_finalize_when_extraction_failed_after_retry_spent(self):
        assert route_after_extract({"extraction": None, "retried": True}) == "finalize"


class TestRouteAfterCritique:
    def test_routes_to_retry_when_needed(self):
        assert route_after_critique({"needs_retry": True}) == "retry"

    def test_routes_to_finalize_when_no_leadership_missing_linkedin(self):
        assert route_after_critique({"needs_retry": False}) == "finalize"
        assert route_after_critique({}) == "finalize"
        state = {"needs_retry": False, "cleaned_leadership": [TeamMember(name="Jane", linkedin_url="https://linkedin.com/in/jane")]}
        assert route_after_critique(state) == "finalize"

    def test_routes_to_linkedin_search_when_a_leader_is_missing_a_url(self):
        state = {"needs_retry": False, "cleaned_leadership": [TeamMember(name="Jane", linkedin_url=None)]}
        assert route_after_critique(state) == "linkedin_search"

    def test_retry_takes_priority_over_linkedin_search(self):
        state = {"needs_retry": True, "cleaned_leadership": [TeamMember(name="Jane", linkedin_url=None)]}
        assert route_after_critique(state) == "retry"


class TestCritiqueNodeRetryGate:
    """The retry budget is spent exactly once: critique_node must never
    request a second retry once state["retried"] is already True, even if
    the underlying critique() call would otherwise want one."""

    def _unusable_extraction(self):
        return ExtractionResult(
            company_overview="",
            target_audience="",
            contact_emails=[],
            leadership=[],
            confidence_score=0.1,
        )

    def test_requests_retry_on_first_unusable_result(self):
        state = {
            "extraction": self._unusable_extraction(),
            "combined_text": "some scraped text",
            "retried": False,
        }
        result = critique_node(state)
        assert result["needs_retry"] is True

    def test_does_not_request_second_retry(self):
        state = {
            "extraction": self._unusable_extraction(),
            "combined_text": "some scraped text",
            "retried": True,
        }
        result = critique_node(state)
        assert result["needs_retry"] is False


class TestFinalizeNode:
    def test_no_pages_produces_failed_status(self):
        result = finalize_node({"domain": "acme.com", "pages": {}, "scrape_errors": ["timeout"]})
        intel = result["result"]
        assert intel.status == "failed"
        assert "timeout" in intel.error

    def test_no_extraction_produces_failed_status(self):
        result = finalize_node(
            {
                "domain": "acme.com",
                "pages": {"https://acme.com": "<html></html>"},
                "extraction": None,
                "extraction_error": "LLM call failed: timeout",
            }
        )
        intel = result["result"]
        assert intel.status == "failed"
        assert intel.error == "LLM call failed: timeout"

    def test_both_fields_present_is_success(self):
        result = finalize_node(
            {
                "domain": "acme.com",
                "pages": {"https://acme.com": "<html></html>"},
                "extraction": ExtractionResult(
                    company_overview="Acme builds widgets.",
                    target_audience="Enterprises.",
                    confidence_score=0.9,
                ),
                "cleaned_emails": [],
                "cleaned_leadership": [],
                "confidence_score": 0.9,
                "critique_notes": [],
            }
        )
        intel = result["result"]
        assert intel.status == "success"

    def test_scrape_warnings_surface_as_critique_notes_on_success(self):
        # A subpage-level bot-block warning shouldn't just vanish into the
        # logs -- it should still be visible on an otherwise-successful result.
        result = finalize_node(
            {
                "domain": "acme.com",
                "pages": {"https://acme.com": "<html></html>"},
                "scrape_errors": ["Subpage (https://acme.com/team) HTTP 403 (commonly a bot-block or rate-limit response) -- content kept but may be unusable"],
                "extraction": ExtractionResult(
                    company_overview="Acme builds widgets.",
                    target_audience="Enterprises.",
                    confidence_score=0.9,
                ),
                "cleaned_emails": [],
                "cleaned_leadership": [],
                "confidence_score": 0.9,
                "critique_notes": [],
            }
        )
        intel = result["result"]
        assert intel.status == "success"
        assert any(note.startswith("Scraper: Subpage") for note in intel.critique_notes)

    def test_one_field_missing_is_partial(self):
        result = finalize_node(
            {
                "domain": "acme.com",
                "pages": {"https://acme.com": "<html></html>"},
                "extraction": ExtractionResult(
                    company_overview="Acme builds widgets.",
                    target_audience="",
                    confidence_score=0.5,
                ),
                "cleaned_emails": [],
                "cleaned_leadership": [],
                "confidence_score": 0.5,
                "critique_notes": [],
            }
        )
        intel = result["result"]
        assert intel.status == "partial"
