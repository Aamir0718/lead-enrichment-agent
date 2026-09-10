"""Critique Agent (deterministic, no LLM by default).

Cross-checks the Extractor's output against the actual scraped source text
to catch hallucinations, recomputes a grounded confidence score, and decides
whether the result is bad enough to warrant exactly one retry through the
Extractor (the only case where this agent triggers an extra LLM call).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from models import ExtractionResult, TeamMember


@dataclass
class CritiqueOutcome:
    cleaned_emails: list[str]
    cleaned_leadership: list[TeamMember]
    confidence_score: float
    notes: list[str] = field(default_factory=list)
    needs_retry: bool = False
    retry_feedback: str | None = None


def _in_source(needle: str, haystack_lower: str) -> bool:
    return needle.lower() in haystack_lower


def critique(extraction: ExtractionResult, combined_text: str) -> CritiqueOutcome:
    notes: list[str] = []
    text_lower = combined_text.lower()

    # --- Cross-check emails against the actual source text ---
    verified_emails = []
    for email in extraction.contact_emails:
        if _in_source(email, text_lower):
            verified_emails.append(email)
        else:
            notes.append(f"Dropped email '{email}': not found verbatim in scraped source (likely hallucinated).")

    # --- Cross-check leadership names against the actual source text ---
    verified_leadership = []
    for member in extraction.leadership:
        if _in_source(member.name, text_lower):
            verified_leadership.append(member)
        else:
            notes.append(f"Dropped leadership entry '{member.name}': name not found in scraped source.")

    # --- Required-field sanity checks ---
    has_overview = bool(extraction.company_overview and extraction.company_overview.strip())
    has_audience = bool(extraction.target_audience and extraction.target_audience.strip())
    if not has_overview:
        notes.append("Missing company overview.")
    if not has_audience:
        notes.append("Missing target audience / ICP.")

    # --- Recompute a grounded confidence score ---
    # Start from the LLM's self-estimate, then penalize for anything we
    # couldn't verify or that was missing outright.
    score = extraction.confidence_score
    dropped_count = len(extraction.contact_emails) - len(verified_emails)
    dropped_count += len(extraction.leadership) - len(verified_leadership)
    if dropped_count:
        score -= 0.1 * dropped_count
    if not has_overview:
        score -= 0.3
    if not has_audience:
        score -= 0.2
    if not verified_emails:
        score -= 0.05
    if not verified_leadership:
        score -= 0.05
    score = max(0.0, min(1.0, round(score, 2)))

    # --- Decide whether a retry is warranted ---
    # Only retry if the output is essentially unusable -- keep LLM calls minimal.
    needs_retry = not has_overview and not has_audience
    retry_feedback = None
    if needs_retry:
        retry_feedback = (
            "Both company_overview and target_audience were empty. "
            "Re-read the provided text and produce a real summary and ICP "
            "even if brief -- do not leave these fields blank."
        )

    return CritiqueOutcome(
        cleaned_emails=verified_emails,
        cleaned_leadership=verified_leadership,
        confidence_score=score,
        notes=notes,
        needs_retry=needs_retry,
        retry_feedback=retry_feedback,
    )
