"""Scraper Agent (deterministic, no LLM).

Responsible for: fetching a domain's homepage with a headless browser,
discovering likely-useful subpages, visiting them, and returning raw HTML.
Never raises on a per-page failure -- logs and moves on so one bad domain
(or one bad subpage) can't crash the whole run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Keywords used to rank <a> links found on the homepage. Higher score = more
# likely to contain the info we care about (team/contact/pricing info).
SUBPAGE_KEYWORDS = {
    "about": 3,
    "team": 3,
    "company": 2,
    "leadership": 3,
    "contact": 2,
    "pricing": 1,
}

MAX_SUBPAGES = 4
NAV_TIMEOUT_MS = 15_000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class ScrapeResult:
    domain: str
    pages: dict[str, str] = field(default_factory=dict)  # url -> raw html
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.pages) > 0


def _normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"
    return domain.rstrip("/")


def _same_site(base_url: str, candidate_url: str) -> bool:
    base_host = urlparse(base_url).netloc.replace("www.", "")
    cand_host = urlparse(candidate_url).netloc.replace("www.", "")
    return base_host == cand_host


def _rank_subpage_links(page, base_url: str) -> list[str]:
    """Inspect anchor tags on the loaded page and rank candidate subpages."""
    try:
        anchors = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => ({href: e.href, text: e.innerText}))"
        )
    except PlaywrightError as exc:
        logger.warning("Could not read links on %s: %s", base_url, exc)
        return []

    scored: dict[str, int] = {}
    for a in anchors:
        href = a.get("href") or ""
        if not href or not _same_site(base_url, href):
            continue
        haystack = f"{href} {a.get('text', '')}".lower()
        score = sum(weight for kw, weight in SUBPAGE_KEYWORDS.items() if kw in haystack)
        if score > 0:
            clean_url = href.split("#")[0].rstrip("/")
            scored[clean_url] = max(scored.get(clean_url, 0), score)

    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    return [url for url, _ in ranked[:MAX_SUBPAGES]]


def scrape_domain(domain: str) -> ScrapeResult:
    """Fetch homepage + up to MAX_SUBPAGES relevant subpages for a domain."""
    base_url = _normalize_domain(domain)
    result = ScrapeResult(domain=domain)

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError as exc:
            result.errors.append(f"Failed to launch browser: {exc}")
            return result

        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.set_default_timeout(NAV_TIMEOUT_MS)

            # 1. Homepage
            try:
                page.goto(base_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(1000)  # let JS-rendered content settle
                result.pages[base_url] = page.content()
            except PlaywrightError as exc:
                result.errors.append(f"Homepage fetch failed ({base_url}): {exc}")
                # No homepage means we likely can't discover subpages either.
                return result

            # 2. Discover + visit subpages
            subpage_urls = _rank_subpage_links(page, base_url)
            for url in subpage_urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    page.wait_for_timeout(500)
                    status = page.evaluate("() => document.title") is not None
                    if status:
                        result.pages[url] = page.content()
                except PlaywrightError as exc:
                    result.errors.append(f"Subpage fetch failed ({url}): {exc}")
                    continue  # never let one bad subpage kill the run

        finally:
            browser.close()

    return result
