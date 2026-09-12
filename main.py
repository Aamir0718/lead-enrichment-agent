"""Main Agent / orchestrator -- CLI entry point.

Runs the LangGraph pipeline (Scraper -> Processor -> Extractor -> Critique,
see graph.py) for each input domain, aggregates results, and writes
output.json. A failure on any single domain is caught and recorded -- it
never stops the batch.

Domains run concurrently (bounded by MAX_CONCURRENT_DOMAINS) since each
domain's pipeline is fully independent -- each gets its own Playwright
browser instance (see agents/scraper.py), so there's no shared state to
worry about between threads.

Usage:
    python main.py                          # runs the 3 default test domains
    python main.py postman.com supabase.com # runs custom domains

For a browser-based experience (enter domains, watch results appear, no
further terminal use) run `uvicorn server:app --reload` instead -- see
server.py and README.md.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

# Scraped site text can contain characters outside the Windows console's
# default cp1252 codepage (smart quotes, arrows, emoji in marketing copy).
# Reconfigure stdout/stderr to UTF-8 so logging never crashes the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from graph import stream_pipeline
from models import CompanyIntel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

DEFAULT_DOMAINS = ["postman.com", "supabase.com", "vapi.ai"]
OUTPUT_PATH = Path(__file__).parent / "output.json"
MAX_CONCURRENT_DOMAINS = int(os.environ.get("MAX_CONCURRENT_DOMAINS", "3"))


def run_domain(domain: str) -> CompanyIntel:
    """Run the LangGraph pipeline for a single domain, logging every step
    as it happens (not just a start/done line) -- this is the CLI's proof
    of what the agent actually did. Never raises.

    Log lines are prefixed with the domain since, with concurrent domains,
    multiple pipelines interleave their output in the console."""
    logger.info("=== Processing %s ===", domain)
    intel: CompanyIntel | None = None
    try:
        for event in stream_pipeline(domain):
            if event["type"] == "log":
                logger.info("  [%s] %s", domain, event["message"])
            else:
                intel = event["result"]
    except Exception as exc:  # noqa: BLE001 -- last-resort guard so one domain never kills the batch
        logger.exception("Unexpected error processing %s", domain)
        return CompanyIntel(domain=domain, status="failed", error=f"Unexpected error: {exc}")

    if intel is None:
        return CompanyIntel(domain=domain, status="failed", error="Pipeline produced no result")

    logger.info(
        "Done %s: status=%s confidence=%.2f emails=%d leadership=%d llm_calls=%d",
        intel.domain, intel.status, intel.confidence_score,
        len(intel.contact_emails), len(intel.leadership), intel.llm_calls_used,
    )
    return intel


def main() -> None:
    domains = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_DOMAINS
    workers = max(1, min(MAX_CONCURRENT_DOMAINS, len(domains)))
    logger.info(
        "Starting lead enrichment run for %d domain(s), up to %d concurrently: %s",
        len(domains), workers, domains,
    )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # executor.map preserves input order in the results list even
        # though domains may finish out of order.
        results = list(executor.map(run_domain, domains))

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
