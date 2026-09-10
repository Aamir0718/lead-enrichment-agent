# Lead Enrichment Agent

A pipeline that takes a list of company domains, crawls their public web
presence with a headless browser, and uses an LLM to extract structured
company intelligence: overview, target audience/ICP, public contact emails,
leadership team, and a data confidence score. Orchestrated as a
[LangGraph](https://github.com/langchain-ai/langgraph) state graph, with a
React results viewer.

## Architecture

The pipeline is split into four single-purpose agents wired together as a
LangGraph `StateGraph` (`graph.py`) instead of hand-rolled if/else control
flow. Only the node that genuinely needs reasoning (extraction) calls an LLM
by default, to keep cost and latency minimal.

```
graph.py -- compiled LangGraph pipeline, run once per domain

  ┌─────────┐  no pages   ┌──────────┐
  │ scrape  │────────────▶│ finalize │
  └────┬────┘             └────▲─────┘
       │ pages found            │
       ▼                        │ parse/API error
  ┌─────────┐             ┌─────┴─────┐
  │ process │───────────▶│  extract   │◀────────┐
  └─────────┘             └─────┬─────┘          │
                                 │ parsed ok       │ retry
                                 ▼                 │
                           ┌───────────┐     ┌─────┴────┐
                           │ critique  │────▶│  retry   │
                           └─────┬─────┘ yes └──────────┘
                                 │ no (or already retried)
                                 ▼
                           ┌───────────┐
                           │ finalize  │
                           └───────────┘
```

| Node | Agent | LLM? | What it does |
|---|---|---|---|
| `scrape` | Scraper | No | Playwright: homepage + up to 4 relevant subpages (about/team/company/contact/pricing) |
| `process` | Processor | No | BeautifulSoup: strips scripts/styles/nav, produces clean bounded text + regex ground-truth emails |
| `extract` | Extractor | **Yes, 1 call** | Groq (Llama via `openai/gpt-oss-120b`): structured JSON extraction validated with Pydantic |
| `critique` | Critique | No (by default) | Cross-checks emails/names against the actual scraped text to catch hallucinations, recomputes a grounded confidence score. Requests exactly ONE retry back through `extract` if the result is unusable (both overview and ICP empty) |
| `retry` | - | No | Marks the one-time retry budget as spent, then loops back to `extract` |
| `finalize` | Main | No | Aggregates node state into the final `CompanyIntel` record |

Worst case: 2 LLM calls per domain. Typical case: 1. Every node's own
external calls (page navigation, LLM request) are wrapped in try/except, and
`main.py` wraps the whole graph invocation per domain again -- a single
domain's failure (bot block, timeout, 404, malformed LLM output) never stops
the batch. It's recorded with `status: "failed"` and an `error` message
instead.

The agent modules themselves (`agents/scraper.py`, `processor.py`,
`extractor.py`, `critique.py`) are framework-agnostic plain functions --
`graph.py` is a thin orchestration layer on top of them, so the same
functions could be re-wired into a different graph shape without touching
their internals.

## Setup (backend)

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure environment variables**

   Copy `.env.example` to `.env` and add your Groq API key (free tier
   available at https://console.groq.com/keys):

   ```bash
   cp .env.example .env
   # then edit .env and set GROQ_API_KEY=...
   ```

3. **Run**

   ```bash
   python main.py
   ```

   This runs the pipeline against the default test domains
   (`postman.com`, `supabase.com`, `vapi.ai`), writes `output.json`, and
   syncs a copy into `frontend/src/data/output.json` for the React app.

   To run against your own domains instead:

   ```bash
   python main.py example.com another-company.com
   ```

## Setup (frontend)

The `frontend/` directory is a Vite + React app that renders `output.json`
as a light, premium results page (Geist / Geist Mono typography, a single
accent color, per-domain cards, and a Download JSON button). It reads
whatever is currently in `frontend/src/data/output.json`, which `main.py`
keeps in sync automatically after every run.

```bash
cd frontend
npm install
npm run dev        # local dev server, e.g. http://localhost:5173
```

For a production build:

```bash
npm run build       # outputs to frontend/dist
npm run preview     # serves that build locally to view it
```

Note: browsers block ES module scripts from running directly off
`file://`, so `dist/index.html` needs to be served (`npm run preview`, or
any static file server) rather than double-clicked -- this is a browser
restriction on all Vite/webpack-built apps, not specific to this project.

## Output format

`output.json` is a list of objects, one per domain:

```json
{
  "domain": "postman.com",
  "status": "success",
  "error": null,
  "company_overview": "...",
  "target_audience": "...",
  "contact_emails": ["support@postman.com"],
  "leadership": [
    {"name": "...", "role": "...", "linkedin_url": "..."}
  ],
  "confidence_score": 0.75,
  "critique_notes": [],
  "pages_scraped": ["https://postman.com", "https://postman.com/company"],
  "llm_calls_used": 1
}
```

`status` is one of `success`, `partial` (some fields missing), or `failed`
(scrape or extraction did not produce usable data -- see `error`).

## Project structure

```
main.py              Entry point: runs graph.py per domain, writes output.json,
                      syncs frontend/src/data/output.json
graph.py              LangGraph StateGraph wiring the four agents together
models.py             Pydantic schemas (ExtractionResult, CompanyIntel, TeamMember)
agents/
  scraper.py          Scraper Agent -- Playwright, subpage discovery, no LLM
  processor.py         Processor Agent -- HTML cleaning + email regex, no LLM
  extractor.py         Extractor Agent -- the only LLM call in the normal path
  critique.py           Critique Agent -- deterministic hallucination/QA check
requirements.txt
.env.example
output.json           Sample output from a run against the 3 test domains
frontend/             Vite + React results viewer
  src/App.jsx           Page layout, run-level stats
  src/components/       Header, StatsBar, ResultCard, StatusPill
  src/data/output.json  Synced copy of the root output.json (read at build/run time)
```

## Notes on resilience

- Every network call (page navigation, LLM request) is wrapped in
  try/except; a failure is logged and the pipeline moves on.
- Subpage discovery is link-based (keyword-ranked `<a>` tags), so it
  degrades gracefully on sites with a different layout instead of hardcoding
  URL paths.
- The Critique Agent's email/name cross-check exists specifically to catch
  LLM hallucination -- it never trusts the model's output blindly, and the
  final confidence score is recomputed from actual evidence rather than
  taken as-is from the LLM.
- `main.py` catches any exception from a domain's graph run (not just the
  errors the nodes anticipate) so one bad domain can never crash the batch.
