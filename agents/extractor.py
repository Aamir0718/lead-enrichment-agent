"""Extractor Agent -- the ONLY agent that calls an LLM in the normal path.

Takes cleaned page text and asks the LLM to return structured JSON matching
`ExtractionResult`. One call per domain in the typical case; the Critique
Agent may ask for exactly one retry (with corrective feedback) if this
output fails validation.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from groq import Groq
from pydantic import ValidationError

from models import ExtractionResult

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = """You are a precise company-research extraction engine.
You will be given cleaned text scraped from a company's public website
(homepage + subpages such as about/team/contact/pricing).

Extract ONLY information that is explicitly present in the given text.
Never invent names, emails, titles, or LinkedIn URLs. If something is not
present, omit it (use an empty list) rather than guessing.

Respond with a single JSON object and nothing else, matching exactly this
shape:
{
  "company_overview": "<2 concise sentences on what the company does>",
  "target_audience": "<who the product is built for, e.g. 'Developers building backend APIs'>",
  "contact_emails": ["<generic public emails found verbatim in the text, e.g. contact@, sales@, support@>"],
  "leadership": [{"name": "<full name>", "role": "<title if stated>", "linkedin_url": "<url if present in text, else null>"}],
  "confidence_score": <float 0.0-1.0, your own honest estimate of how complete/reliable this extraction is given what was actually available in the text>
}
"""


def _strip_code_fences(raw: str) -> str:
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if match:
        return match.group(1)
    return raw


def extract(
    domain: str,
    combined_text: str,
    feedback: Optional[str] = None,
) -> tuple[Optional[ExtractionResult], Optional[str]]:
    """Run one LLM extraction call. Returns (result, error_message)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None, "GROQ_API_KEY not set in environment"

    if not combined_text.strip():
        return None, "No content was scraped for this domain"

    user_prompt = f"Domain: {domain}\n\nScraped site text:\n{combined_text}"
    if feedback:
        user_prompt += (
            f"\n\n[Retry instruction from Critique Agent]: Your previous "
            f"attempt had an issue: {feedback}. Please correct it and "
            f"respond with valid JSON only."
        )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001 -- any provider/network error must not crash the run
        return None, f"LLM call failed: {exc}"

    raw_content = response.choices[0].message.content or ""
    cleaned = _strip_code_fences(raw_content).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"LLM did not return valid JSON: {exc}"

    try:
        result = ExtractionResult(**data)
    except ValidationError as exc:
        return None, f"LLM output failed schema validation: {exc}"

    return result, None
