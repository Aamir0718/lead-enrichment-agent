"""Main Agent / orchestrator -- CLI entry point.

Runs the LangGraph pipeline (Scraper -> Processor -> Extractor -> Critique,
see graph.py) for each input domain, aggregates results, and writes
output.json. A failure on any single domain is caught and recorded -- it
never stops the batch.

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
import sys
from pathlib import Path

from dotenv import load_dotenv

# Scraped site text can contain characters outside the Windows console's
# default cp1252 codepage (smart quotes, arrows, emoji in marketing copy).
# Reconfigure stdout/stderr to UTF-8 so logging never crashes the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from graph import run_pipeline
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
    """Run the LangGraph pipeline for a single domain. Never raises."""
    logger.info("=== Processing %s ===", domain)
    try:
        intel = run_pipeline(domain)
        logger.info(
            "Done %s: status=%s confidence=%.2f emails=%d leadership=%d llm_calls=%d",
            intel.domain, intel.status, intel.confidence_score,
            len(intel.contact_emails), len(intel.leadership), intel.llm_calls_used,
        )
        return intel
    except Exception as exc:  # noqa: BLE001 -- last-resort guard so one domain never kills the batch
        logger.exception("Unexpected error processing %s", domain)
        return CompanyIntel(domain=domain, status="failed", error=f"Unexpected error: {exc}")


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
