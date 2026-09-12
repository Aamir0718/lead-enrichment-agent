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
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from graph import stream_pipeline
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
MAX_CONCURRENT_DOMAINS = int(os.environ.get("MAX_CONCURRENT_DOMAINS", "3"))
SSE_POLL_INTERVAL_SECONDS = 0.3

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
    so the frontend can render cards progressively, not just at the end.
    `logs` is the same step-by-step trail main.py prints to the console,
    captured here so the browser has the same visibility into what's
    actually happening instead of a silent spinner. `in_progress` exists
    because domains now run concurrently (bounded by
    MAX_CONCURRENT_DOMAINS) -- more than one can be actively running at
    once, so the frontend needs to know which ones, not just assume the
    first not-yet-done domain is the one running."""

    def __init__(self, domains: list[str]):
        self.id = uuid.uuid4().hex
        self.order = domains
        self.status = "running"  # running | done
        self.results: dict[str, CompanyIntel] = {}
        self.logs: list[dict] = []
        self.in_progress: set[str] = set()


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _log(job: Job, message: str) -> None:
    with _jobs_lock:
        job.logs.append({"ts": time.time(), "message": message})
    logger.info("Job %s: %s", job.id, message)


def _run_one_domain(job: Job, domain: str) -> None:
    """Runs a single domain's pipeline and records its result. Never
    raises -- one bad domain must never take the rest of the job down."""
    with _jobs_lock:
        job.in_progress.add(domain)

    intel: Optional[CompanyIntel] = None
    try:
        for event in stream_pipeline(domain):
            if event["type"] == "log":
                _log(job, f"[{domain}] {event['message']}")
            else:
                intel = event["result"]
    except Exception as exc:  # noqa: BLE001 -- one bad domain must never kill the job
        logger.exception("Unexpected error processing %s", domain)
        _log(job, f"[{domain}] Unexpected error: {exc}")
        intel = CompanyIntel(domain=domain, status="failed", error=f"Unexpected error: {exc}")

    if intel is None:
        intel = CompanyIntel(domain=domain, status="failed", error="Pipeline produced no result")

    with _jobs_lock:
        job.in_progress.discard(domain)
        job.results[domain] = intel


def _execute_job(job: Job) -> None:
    """Runs the job's domains concurrently (bounded by
    MAX_CONCURRENT_DOMAINS), in a background thread.

    Playwright's sync API (used by the Scraper Agent) can't run inside a
    thread that already has an asyncio event loop -- this whole function
    runs in a plain background thread started by start_enrich() (not an
    asyncio task), and a nested ThreadPoolExecutor's workers are plain OS
    threads too, so both levels are safe by the same reasoning. Actual LLM
    calls are paced separately (see agents/extractor.py's throttle) to stay
    under Groq's rate limit regardless of how many domains scrape at once.
    """
    workers = max(1, min(MAX_CONCURRENT_DOMAINS, len(job.order)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(lambda domain: _run_one_domain(job, domain), job.order))

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


def _get_job_or_404(job_id: str) -> Job:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_snapshot(job: Job) -> dict:
    with _jobs_lock:
        results = [job.results[d].model_dump() for d in job.order if d in job.results]
        return {
            "job_id": job.id,
            "status": job.status,
            "domains": job.order,
            "completed": len(results),
            "total": len(job.order),
            "results": results,
            "logs": list(job.logs),
            "in_progress": list(job.in_progress),
        }


@app.get("/api/enrich/{job_id}")
def get_enrich_status(job_id: str):
    return _job_snapshot(_get_job_or_404(job_id))


@app.get("/api/enrich/{job_id}/stream")
def stream_enrich_status(job_id: str):
    """Server-Sent Events version of the status endpoint -- pushes a fresh
    snapshot the moment anything changes instead of making the browser poll
    on a fixed interval. Internally this still checks the in-memory job on
    a short timer (SSE_POLL_INTERVAL_SECONDS) rather than being truly
    event-driven end to end; that's an honest trade-off for this scope --
    a full pub/sub rewrite would be over-engineering for a single-process
    app, and this already cuts perceived latency from ~1.2s to ~0.3s while
    using one long-lived connection instead of repeated HTTP requests."""
    job = _get_job_or_404(job_id)

    def event_stream():
        last_payload = None
        while True:
            snapshot = _job_snapshot(job)
            payload = json.dumps(snapshot)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if snapshot["status"] == "done":
                yield "event: done\ndata: {}\n\n"
                return
            time.sleep(SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/results")
def get_last_results():
    """Whatever the most recent run (CLI or API) produced, if anything."""
    if not OUTPUT_PATH.exists():
        return []
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


@app.middleware("http")
async def no_cache_html_shell(request, call_next):
    """Vite's built JS/CSS filenames are content-hashed, so browsers are
    free to cache those aggressively -- but index.html itself has no hash,
    and a cached copy pointing at a since-deleted hashed filename (from a
    previous build) causes exactly the confusing 404s this is meant to
    prevent. Only the HTML shell is exempted from caching; hashed assets
    are untouched."""
    response = await call_next(request)
    if request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


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
