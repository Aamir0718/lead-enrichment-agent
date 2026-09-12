"""Critique Agent (deterministic, no LLM by default).

Cross-checks the Extractor's output against the actual scraped source text
to catch hallucinations, recomputes a grounded confidence score, and decides
whether the result is bad enough to warrant exactly one retry through the
Extractor (the only case where this agent triggers an extra LLM call).

Emails are verified against the Processor's `raw_emails_found` (already
regex-confirmed-present AND filtered to generic/public-looking addresses),
not a raw substring search -- this is what actually enforces the
assignment's "generic or public emails" spec rather than accepting any
address the LLM happens to name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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


def critique(
    extraction: ExtractionResult,
    combined_text: str,
    raw_emails_found: Optional[list[str]] = None,
) -> CritiqueOutcome:
    notes: list[str] = []
    text_lower = combined_text.lower()
    generic_emails = {e.lower() for e in (raw_emails_found or [])}

    # --- Cross-check emails against the Processor's deterministic,
    # generic-filtered regex scan (not a raw substring check) -- this
    # verifies both "is this real" (present on the page) and "is this the
    # kind of email the assignment asks for" (contact@/sales@/support@-style,
    # not a named individual's address) in one step. ---
    verified_emails = [e for e in extraction.contact_emails if e.lower() in generic_emails]
    dropped_email_count = len(extraction.contact_emails) - len(verified_emails)
    for email in extraction.contact_emails:
        if email.lower() not in generic_emails:
            notes.append(
                f"Dropped email '{email}': not found among the generic/public emails detected on the page."
            )

    # Resilience fallback: a plain regex scan can find an obviously public
    # email even when the LLM's extraction missed it entirely. Don't let a
    # trivially-detectable fact go unreported just because the model didn't
    # mention it.
    if not verified_emails and generic_emails:
        verified_emails = sorted(generic_emails)
        notes.append(
            f"LLM reported no emails; added {len(verified_emails)} generic email(s) found directly via regex scan."
        )

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
    dropped_count = dropped_email_count + (len(extraction.leadership) - len(verified_leadership))
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
