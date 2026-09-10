"""Main Agent / orchestrator.

Runs the full pipeline (Scraper -> Processor -> Extractor -> Critique) for
each input domain, aggregates results, and writes output.json. A failure on
any single domain is caught and recorded -- it never stops the batch.

Usage:
    python main.py                          # runs the 3 default test domains
    python main.py postman.com supabase.com # runs custom domains
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Scraped site text can contain characters outside the Windows console's
# default cp1252 codepage (smart quotes, arrows, emoji in marketing copy).
# Reconfigure stdout/stderr to UTF-8 so logging never crashes the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from agents.critique import critique
from agents.extractor import extract
from agents.processor import process_pages
from agents.scraper import scrape_domain
from models import CompanyIntel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

DEFAULT_DOMAINS = ["postman.com", "supabase.com", "vapi.ai"]
OUTPUT_PATH = Path(__file__).parent / "output.json"


def run_domain(domain: str) -> CompanyIntel:
    """Run the full pipeline for a single domain. Never raises."""
    logger.info("=== Processing %s ===", domain)
    intel = CompanyIntel(domain=domain)

    try:
        # --- Stage 1: Scraper Agent (deterministic) ---
        scrape_result = scrape_domain(domain)
        intel.pages_scraped = list(scrape_result.pages.keys())
        if not scrape_result.ok:
            intel.status = "failed"
            intel.error = "; ".join(scrape_result.errors) or "No pages could be fetched"
            logger.warning("Scrape failed for %s: %s", domain, intel.error)
            return intel

        # --- Stage 2: Processor Agent (deterministic) ---
        processed = process_pages(scrape_result.pages)

        # --- Stage 3: Extractor Agent (LLM, call #1) ---
        result, err = extract(domain, processed.combined_text)
        intel.llm_calls_used += 1
        if err or result is None:
            intel.status = "failed"
            intel.error = err
            logger.warning("Extraction failed for %s: %s", domain, err)
            return intel

        # --- Stage 4: Critique Agent (deterministic, may trigger 1 retry) ---
        outcome = critique(result, processed.combined_text)

        if outcome.needs_retry:
            logger.info("Critique requested one retry for %s: %s", domain, outcome.retry_feedback)
            retry_result, retry_err = extract(domain, processed.combined_text, feedback=outcome.retry_feedback)
            intel.llm_calls_used += 1
            if retry_result is not None:
                result = retry_result
                outcome = critique(result, processed.combined_text)  # re-validate, no further retries allowed
            else:
                outcome.notes.append(f"Retry also failed: {retry_err}")

        intel.company_overview = result.company_overview
        intel.target_audience = result.target_audience
        intel.contact_emails = outcome.cleaned_emails
        intel.leadership = outcome.cleaned_leadership
        intel.confidence_score = outcome.confidence_score
        intel.critique_notes = outcome.notes

        has_overview = bool(intel.company_overview and intel.company_overview.strip())
        has_audience = bool(intel.target_audience and intel.target_audience.strip())
        if has_overview and has_audience:
            intel.status = "success"
        elif has_overview or has_audience:
            intel.status = "partial"
        else:
            intel.status = "failed"
            intel.error = intel.error or "Usable overview/ICP could not be extracted after retry"

        logger.info(
            "Done %s: status=%s confidence=%.2f emails=%d leadership=%d llm_calls=%d",
            domain, intel.status, intel.confidence_score,
            len(intel.contact_emails), len(intel.leadership), intel.llm_calls_used,
        )

    except Exception as exc:  # noqa: BLE001 -- last-resort guard so one domain never kills the batch
        logger.exception("Unexpected error processing %s", domain)
        intel.status = "failed"
        intel.error = f"Unexpected error: {exc}"

    return intel


def main() -> None:
    domains = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_DOMAINS
    logger.info("Starting lead enrichment run for %d domain(s): %s", len(domains), domains)

    results = [run_domain(domain) for domain in domains]

    OUTPUT_PATH.write_text(
        json.dumps([r.model_dump() for r in results], indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote results to %s", OUTPUT_PATH)

    total_llm_calls = sum(r.llm_calls_used for r in results)
    print("\n=== Run Summary ===")
    for r in results:
        print(f"  {r.domain:20s} status={r.status:8s} confidence={r.confidence_score:.2f} llm_calls={r.llm_calls_used}")
    print(f"\nTotal LLM calls used: {total_llm_calls}")
    print(f"Output written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
