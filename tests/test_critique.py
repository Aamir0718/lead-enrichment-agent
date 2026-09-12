"""Tests for the Critique Agent (agents/critique.py) -- deterministic
hallucination-detection and confidence-scoring logic."""
from agents.critique import critique
from models import ExtractionResult, TeamMember


def make_extraction(**overrides):
    defaults = dict(
        company_overview="Acme builds widgets for enterprises.",
        target_audience="Enterprise procurement teams.",
        contact_emails=[],
        leadership=[],
        confidence_score=0.8,
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


SOURCE_TEXT = (
    "--- Source: https://acme.com ---\n"
    "Acme builds widgets. Contact us at sales@acme.com.\n"
    "Our CEO Jane Smith leads the company."
)


class TestEmailVerification:
    def test_hallucinated_email_is_dropped(self):
        # No raw_emails_found candidates at all, so the "LLM reported none"
        # fallback can't mask the drop -- isolates the hallucination check.
        extraction = make_extraction(contact_emails=["fake@acme.com"])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.cleaned_emails == []
        assert any("fake@acme.com" in note for note in outcome.notes)

    def test_hallucinated_email_falls_back_to_a_real_one_if_available(self):
        # If the LLM's claimed email doesn't check out but the deterministic
        # scan found a different real, generic email, that's still worth
        # surfacing rather than reporting nothing.
        extraction = make_extraction(contact_emails=["fake@acme.com"])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=["sales@acme.com"])
        assert outcome.cleaned_emails == ["sales@acme.com"]

    def test_genuinely_present_generic_email_is_kept(self):
        extraction = make_extraction(contact_emails=["sales@acme.com"])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=["sales@acme.com"])
        assert outcome.cleaned_emails == ["sales@acme.com"]
        assert outcome.notes == []

    def test_case_insensitive_match(self):
        extraction = make_extraction(contact_emails=["Sales@Acme.com"])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=["sales@acme.com"])
        assert outcome.cleaned_emails == ["Sales@Acme.com"]

    def test_fallback_adds_regex_found_emails_when_llm_reports_none(self):
        extraction = make_extraction(contact_emails=[])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=["sales@acme.com"])
        assert outcome.cleaned_emails == ["sales@acme.com"]
        assert any("added" in note.lower() for note in outcome.notes)

    def test_no_fallback_when_nothing_found_at_all(self):
        extraction = make_extraction(contact_emails=[])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.cleaned_emails == []


class TestLeadershipVerification:
    def test_present_leader_is_kept(self):
        extraction = make_extraction(leadership=[TeamMember(name="Jane Smith", role="CEO")])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert len(outcome.cleaned_leadership) == 1
        assert outcome.cleaned_leadership[0].name == "Jane Smith"

    def test_absent_leader_is_dropped(self):
        extraction = make_extraction(leadership=[TeamMember(name="John Doe", role="CTO")])
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.cleaned_leadership == []
        assert any("John Doe" in note for note in outcome.notes)


class TestConfidenceScoring:
    def test_clean_result_keeps_llm_confidence(self):
        # Populate emails/leadership too -- an extraction with genuinely
        # nothing to report there still takes a small penalty (tested
        # separately), so isolate "nothing was dropped" from "nothing was
        # ever claimed" here.
        extraction = make_extraction(
            contact_emails=["sales@acme.com"],
            leadership=[TeamMember(name="Jane Smith", role="CEO")],
            confidence_score=0.8,
        )
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=["sales@acme.com"])
        assert outcome.confidence_score == 0.8

    def test_reporting_nothing_found_is_penalized(self):
        extraction = make_extraction(contact_emails=[], leadership=[], confidence_score=0.8)
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.confidence_score < 0.8

    def test_missing_overview_penalized(self):
        extraction = make_extraction(company_overview="", confidence_score=0.8)
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.confidence_score < 0.8

    def test_missing_audience_penalized(self):
        extraction = make_extraction(target_audience="", confidence_score=0.8)
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.confidence_score < 0.8

    def test_dropped_item_penalized(self):
        extraction = make_extraction(contact_emails=["fake@acme.com"], confidence_score=0.9)
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.confidence_score < 0.9

    def test_score_never_goes_below_zero(self):
        extraction = make_extraction(
            company_overview="",
            target_audience="",
            contact_emails=["fake@acme.com", "also-fake@acme.com"],
            leadership=[TeamMember(name="Nobody Real")],
            confidence_score=0.1,
        )
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.confidence_score == 0.0


class TestRetryDecision:
    def test_needs_retry_when_both_overview_and_audience_missing(self):
        extraction = make_extraction(company_overview="", target_audience="")
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.needs_retry is True
        assert outcome.retry_feedback is not None

    def test_no_retry_when_only_one_field_missing(self):
        extraction = make_extraction(company_overview="", target_audience="Enterprise teams.")
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.needs_retry is False

    def test_no_retry_when_both_fields_present(self):
        extraction = make_extraction()
        outcome = critique(extraction, SOURCE_TEXT, raw_emails_found=[])
        assert outcome.needs_retry is False
