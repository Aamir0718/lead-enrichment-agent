"""LinkedIn/founder search Agent (bonus feature, optional).

Fills in a LinkedIn URL for leadership entries that survived the Critique
Agent but weren't found on the company's own site, using an external
search API (Tavily). Entirely optional: no-ops cleanly with no error if
TAVILY_API_KEY isn't configured, and never raises -- a failed search must
never take a domain down.

Same "verify, don't just trust" principle as the rest of the pipeline: a
search hit is only accepted if it's actually shaped like a LinkedIn profile
URL, never blindly whatever the top result happens to be.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

LINKEDIN_PROFILE_RE = re.compile(r"^https://(www\.)?linkedin\.com/in/[^/?#]+/?$", re.IGNORECASE)


def is_configured() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY"))


def find_linkedin_url(name: str, domain: str) -> Optional[str]:
    """Search for a person's LinkedIn profile. Returns None if no API key
    is configured, nothing found, or the search fails -- never raises."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None

    try:
        from tavily import TavilyClient  # imported lazily -- keeps this dependency optional

        client = TavilyClient(api_key=api_key)
        response = client.search(query=f'"{name}" {domain} LinkedIn', max_results=5)
    except Exception as exc:  # noqa: BLE001 -- a failed search must never crash the pipeline
        logger.warning("LinkedIn search failed for %s: %s", name, exc)
        return None

    for result in response.get("results", []):
        url = result.get("url", "")
        if LINKEDIN_PROFILE_RE.match(url):
            return url
    return None
