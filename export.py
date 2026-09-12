"""CSV export for CompanyIntel results (the JSON output's flattened sibling).

The assignment spec accepts either `output.json` or `output.csv` as the
sample output deliverable. `output.json` stays the primary, full-fidelity
format (nested leadership objects, the full `source_text` evidence blob);
this module produces a spreadsheet-friendly flattening of the same records
-- list/object fields become "; "-joined strings, and `source_text` is
dropped entirely since a multi-thousand-character blob per row would make
the CSV unreadable in a spreadsheet, defeating the point of the format.

Kept separate from main.py so it's a pure, easily-testable function (no
CLI/orchestration concerns) that server.py or any other caller could reuse.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from models import CompanyIntel, TeamMember

CSV_FIELDNAMES = [
    "domain",
    "status",
    "error",
    "company_overview",
    "target_audience",
    "contact_emails",
    "leadership",
    "confidence_score",
    "critique_notes",
    "pages_scraped",
    "llm_calls_used",
    "linkedin_calls_used",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "estimated_cost_usd",
]


def _format_leadership(leadership: Iterable[TeamMember]) -> str:
    """"Jane Doe (CEO) - https://linkedin.com/in/jane; ..." -- role and
    LinkedIn URL are each optional, so only include what's actually there."""
    parts = []
    for member in leadership:
        piece = member.name
        if member.role:
            piece += f" ({member.role})"
        if member.linkedin_url:
            piece += f" - {member.linkedin_url}"
        parts.append(piece)
    return "; ".join(parts)


def intel_to_csv_row(intel: CompanyIntel) -> dict:
    """Flatten one CompanyIntel record into a CSV-writable dict of strings/numbers."""
    return {
        "domain": intel.domain,
        "status": intel.status,
        "error": intel.error or "",
        "company_overview": intel.company_overview or "",
        "target_audience": intel.target_audience or "",
        "contact_emails": "; ".join(intel.contact_emails),
        "leadership": _format_leadership(intel.leadership),
        "confidence_score": intel.confidence_score,
        "critique_notes": "; ".join(intel.critique_notes),
        "pages_scraped": "; ".join(intel.pages_scraped),
        "llm_calls_used": intel.llm_calls_used,
        "linkedin_calls_used": intel.linkedin_calls_used,
        "prompt_tokens": intel.prompt_tokens,
        "completion_tokens": intel.completion_tokens,
        "total_tokens": intel.total_tokens,
        "estimated_cost_usd": intel.estimated_cost_usd,
    }


def write_csv(results: Iterable[CompanyIntel], path: Path) -> None:
    """Write `results` to `path` as CSV, one row per domain."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for intel in results:
            writer.writerow(intel_to_csv_row(intel))
