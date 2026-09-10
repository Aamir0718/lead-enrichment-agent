"""API server -- lets the React frontend run the pipeline and view results
entirely from the browser, with no further terminal use after this process
is started.

Wraps the exact same LangGraph pipeline main.py uses (graph.run_pipeline);
this file only adds an HTTP layer and a small in-memory job tracker around
it, plus serving the built frontend so one process is the whole app.

Run it:
    uvicorn server:app --reload
    # then open http://localhost:8000

The CLI (`python main.py domains...`) still exists separately and writes
the same output.json -- use whichever fits the moment.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from graph import run_pipeline
from models import CompanyIntel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("server")

OUTPUT_PATH = Path(__file__).parent / "output.json"
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
MAX_DOMAINS_PER_RUN = 10

app = FastAPI(title="Lead Enrichment Agent API")

# Only relevant when running the frontend separately via `npm run dev`
# (Vite's dev server proxies /api to this process anyway -- see
# frontend/vite.config.js -- so this is a defensive fallback, not the
# primary mechanism).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class EnrichRequest(BaseModel):
    domains: list[str] = Field(min_length=1, max_length=MAX_DOMAINS_PER_RUN)

    @field_validator("domains")
    @classmethod
    def clean_domains(cls, value: list[str]) -> list[str]:
        cleaned = [d.strip() for d in value if d and d.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty domain is required")
        return cleaned


class Job:
    """Tracks one enrichment run. Results fill in per-domain as they finish
    so the frontend can render cards progressively, not just at the end."""

    def __init__(self, domains: list[str]):
        self.id = uuid.uuid4().hex
        self.order = domains
        self.status = "running"  # running | done
        self.results: dict[str, CompanyIntel] = {}


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _execute_job(job: Job) -> None:
    """Runs domains one at a time in a background thread.

    Playwright's sync API (used by the Scraper Agent) can't run inside a
    thread that already has an asyncio event loop -- a plain background
    thread (not an asyncio task) sidesteps that entirely.
    """
    for domain in job.order:
        try:
            intel = run_pipeline(domain)
        except Exception as exc:  # noqa: BLE001 -- one bad domain must never kill the job
            logger.exception("Unexpected error processing %s", domain)
            intel = CompanyIntel(domain=domain, status="failed", error=f"Unexpected error: {exc}")
        with _jobs_lock:
            job.results[domain] = intel
        logger.info("Job %s: %s -> %s", job.id, domain, intel.status)

    with _jobs_lock:
        job.status = "done"
        ordered = [job.results[d] for d in job.order]
        OUTPUT_PATH.write_text(
            json.dumps([r.model_dump() for r in ordered], indent=2),
            encoding="utf-8",
        )
    logger.info("Job %s finished, wrote %s", job.id, OUTPUT_PATH)


@app.post("/api/enrich")
def start_enrich(payload: EnrichRequest):
    job = Job(payload.domains)
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=_execute_job, args=(job,), daemon=True).start()
    return {"job_id": job.id, "domains": job.order}


@app.get("/api/enrich/{job_id}")
def get_enrich_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        results = [job.results[d].model_dump() for d in job.order if d in job.results]
        return {
            "job_id": job.id,
            "status": job.status,
            "domains": job.order,
            "completed": len(results),
            "total": len(job.order),
            "results": results,
        }


@app.get("/api/results")
def get_last_results():
    """Whatever the most recent run (CLI or API) produced, if anything."""
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        return {
            "detail": (
                "Frontend build not found. Run `cd frontend && npm install && npm run build`, "
                "then restart this server."
            )
        }
