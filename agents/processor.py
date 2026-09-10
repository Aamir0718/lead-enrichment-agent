"""Content Processor Agent (deterministic, no LLM).

Strips raw HTML down to clean text so we never feed a full DOM tree to the
LLM (saves tokens + latency, per assignment spec). Also regex-extracts emails
directly from source text as a ground-truth signal the Critique Agent can
cross-check the LLM's output against.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# Tags whose content is never useful for company-intel extraction.
STRIP_TAGS = ["script", "style", "svg", "noscript", "iframe", "path", "img"]

MAX_CHARS_PER_PAGE = 6000  # keep per-page text bounded before concatenation
MAX_TOTAL_CHARS = 18000  # hard cap on combined text sent to the LLM

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Generic/public-looking mailbox prefixes we care about per the assignment.
GENERIC_PREFIXES = ("contact", "sales", "support", "hello", "hi", "info", "team", "press", "careers")


@dataclass
class ProcessedContent:
    combined_text: str
    per_page_text: dict[str, str] = field(default_factory=dict)
    raw_emails_found: set[str] = field(default_factory=set)


def _clean_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse excessive blank lines / whitespace left behind by stripped tags.
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)[:MAX_CHARS_PER_PAGE]


def extract_emails(text: str) -> set[str]:
    found = {m.group(0).lower() for m in EMAIL_RE.finditer(text)}
    # Drop obvious asset/junk matches (e.g. image@2x style false positives already
    # excluded by the regex requiring a TLD, but guard against extremely long
    # "emails" that are really minified JS/CSS artifacts leaking through).
    return {e for e in found if len(e) < 60}


def process_pages(pages: dict[str, str]) -> ProcessedContent:
    """Clean every page's HTML and build one bounded text blob for the LLM."""
    per_page_text: dict[str, str] = {}
    raw_emails: set[str] = set()

    for url, html in pages.items():
        text = _clean_html_to_text(html)
        per_page_text[url] = text
        raw_emails |= extract_emails(text)

    parts = []
    running_total = 0
    for url, text in per_page_text.items():
        header = f"\n\n--- Source: {url} ---\n"
        chunk = header + text
        if running_total + len(chunk) > MAX_TOTAL_CHARS:
            remaining = MAX_TOTAL_CHARS - running_total
            if remaining > len(header):
                parts.append(chunk[:remaining])
            break
        parts.append(chunk)
        running_total += len(chunk)

    return ProcessedContent(
        combined_text="".join(parts).strip(),
        per_page_text=per_page_text,
        raw_emails_found=raw_emails,
    )
