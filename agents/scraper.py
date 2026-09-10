"""Scraper Agent (deterministic, no LLM).

Responsible for: fetching a domain's homepage with a headless browser,
discovering likely-useful subpages, visiting them, and returning raw HTML.
Never raises on a per-page failure -- logs and moves on so one bad domain
(or one bad subpage) can't crash the whole run.

Two resilience details that matter for domains beyond the 3 this project
was demoed against: navigation retries once on transient failures (most
real-world timeouts are a one-off network blip, not a hard block), and
same-site filtering is based on where the homepage actually resolved to
after redirects, not the URL as typed -- otherwise a domain that redirects
to a different host (bare domain -> www, or even a different registrable
domain) would have every subpage silently discarded.
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
NAV_TIMEOUT_MS = 20_000
NAV_RETRY_ATTEMPTS = 2  # transient timeouts/network blips are common; one retry catches most
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


def _goto_with_retry(page, url: str, wait_after_ms: int, attempts: int = NAV_RETRY_ATTEMPTS) -> None:
    """Navigate with up to `attempts` tries. Most real-world failures here
    are transient (a slow DNS lookup, a one-off timeout) rather than a hard
    block, so a single retry meaningfully improves the hit rate on domains
    outside the small set this was hand-tested against. Raises the last
    error if every attempt fails."""
    last_error: PlaywrightError | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(wait_after_ms)  # let JS-rendered content settle
            return
        except PlaywrightError as exc:
            last_error = exc
            logger.warning("Navigation attempt %d/%d failed for %s: %s", attempt, attempts, url, exc)
    raise last_error


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
                _goto_with_retry(page, base_url, wait_after_ms=1000)
                # Use where the page actually landed, not the URL we typed --
                # domains commonly redirect to a different host (bare domain
                # -> www, or even a different registrable domain entirely,
                # e.g. notion.so -> notion.com). Same-site filtering below
                # must be based on the resolved host or every subpage on a
                # redirecting domain gets silently discarded.
                resolved_url = page.url or base_url
                result.pages[resolved_url] = page.content()
            except PlaywrightError as exc:
                result.errors.append(
                    f"Homepage fetch failed after {NAV_RETRY_ATTEMPTS} attempt(s) ({base_url}): {exc}"
                )
                # No homepage means we likely can't discover subpages either.
                return result

            # 2. Discover + visit subpages
            subpage_urls = _rank_subpage_links(page, resolved_url)
            for url in subpage_urls:
                try:
                    _goto_with_retry(page, url, wait_after_ms=500)
                    status = page.evaluate("() => document.title") is not None
                    if status:
                        result.pages[url] = page.content()
                except PlaywrightError as exc:
                    result.errors.append(f"Subpage fetch failed after {NAV_RETRY_ATTEMPTS} attempt(s) ({url}): {exc}")
                    continue  # never let one bad subpage kill the run

        finally:
            browser.close()

    return result
