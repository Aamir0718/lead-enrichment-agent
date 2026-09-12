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
import threading
import time
from dataclasses import dataclass
from typing import Optional

from groq import Groq
from pydantic import ValidationError

from models import ExtractionResult

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# With concurrent domain processing (see main.py/server.py), scraping
# multiple domains at once is safe and fast -- but firing multiple LLM
# calls close together is not: Groq's free/on-demand tier enforces a
# tokens-per-minute limit (8000 TPM at time of writing) and a single
# extraction call already uses ~5000 tokens, so any two calls landing in
# the same rolling minute trip it. Observed in practice: 3 domains scraped
# concurrently, each reaching the Extractor within seconds of each other,
# produced repeated 429s -- reactive SDK retry-with-backoff recovered but
# wasted 30+ seconds per collision. `_throttle_llm_call()` paces calls
# proactively instead, which is strictly cheaper than retrying after the
# fact. Tune down GROQ_MIN_SECONDS_BETWEEN_CALLS (or raise the TPM limit
# via a paid Groq tier) if you have more headroom than the free tier.
_llm_call_lock = threading.Lock()
_last_llm_call_started_at = 0.0
MIN_SECONDS_BETWEEN_LLM_CALLS = float(os.environ.get("GROQ_MIN_SECONDS_BETWEEN_CALLS", "45"))


def _throttle_llm_call() -> None:
    """Block until it's been at least MIN_SECONDS_BETWEEN_LLM_CALLS since
    the last call started. Thread-safe -- this is what actually keeps
    concurrent domains from bursting past Groq's TPM limit."""
    global _last_llm_call_started_at
    with _llm_call_lock:
        now = time.monotonic()
        wait = _last_llm_call_started_at + MIN_SECONDS_BETWEEN_LLM_CALLS - now
        if wait > 0:
            logger.info("Pacing LLM call: waiting %.1fs to stay under Groq's rate limit", wait)
            time.sleep(wait)
        _last_llm_call_started_at = time.monotonic()

# Groq pricing for the default model (openai/gpt-oss-120b), USD per 1M
# tokens, per https://console.groq.com/docs/model/openai/gpt-oss-120b
# (checked Sep 2026). Override via env vars if using a different model or
# if pricing has since changed -- this is an estimate, not a live lookup.
INPUT_COST_PER_1M = float(os.environ.get("GROQ_INPUT_COST_PER_1M", "0.15"))
OUTPUT_COST_PER_1M = float(os.environ.get("GROQ_OUTPUT_COST_PER_1M", "0.60"))


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @classmethod
    def zero(cls) -> "TokenUsage":
        return cls()

    @classmethod
    def from_groq(cls, usage) -> "TokenUsage":
        if usage is None:
            return cls.zero()
        prompt = usage.prompt_tokens or 0
        completion = usage.completion_tokens or 0
        cost = (prompt / 1_000_000) * INPUT_COST_PER_1M + (completion / 1_000_000) * OUTPUT_COST_PER_1M
        return cls(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=usage.total_tokens or (prompt + completion),
            estimated_cost_usd=round(cost, 6),
        )

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
) -> tuple[Optional[ExtractionResult], Optional[str], TokenUsage]:
    """Run one LLM extraction call. Returns (result, error_message, usage).
    `usage` is always a TokenUsage (zeroed if the call never went out) so
    callers never need to null-check it."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None, "GROQ_API_KEY not set in environment", TokenUsage.zero()

    if not combined_text.strip():
        return None, "No content was scraped for this domain", TokenUsage.zero()

    user_prompt = f"Domain: {domain}\n\nScraped site text:\n{combined_text}"
    if feedback:
        user_prompt += (
            f"\n\n[Retry instruction from Critique Agent]: Your previous "
            f"attempt had an issue: {feedback}. Please correct it and "
            f"respond with valid JSON only."
        )

    try:
        _throttle_llm_call()
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
        return None, f"LLM call failed: {exc}", TokenUsage.zero()

    usage = TokenUsage.from_groq(getattr(response, "usage", None))
    raw_content = response.choices[0].message.content or ""
    cleaned = _strip_code_fences(raw_content).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"LLM did not return valid JSON: {exc}", usage

    try:
        result = ExtractionResult(**data)
    except ValidationError as exc:
        return None, f"LLM output failed schema validation: {exc}", usage

    return result, None, usage
