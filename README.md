# Lead Enrichment Agent

A pipeline that takes a list of company domains, crawls their public web
presence with a headless browser, and uses an LLM to extract structured
company intelligence: overview, target audience/ICP, public contact emails,
leadership team, and a data confidence score. Orchestrated as a
[LangGraph](https://github.com/langchain-ai/langgraph) state graph, usable
either as a CLI script or as a full app -- a FastAPI backend plus a React
frontend where you enter domains and watch results appear, no terminal
needed beyond starting the one process.

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

## Run it as an app (no terminal after this)

The intended way to use this project day-to-day: start one process, then do
everything else -- enter domains, run the pipeline, watch results appear,
download the JSON -- from the browser.

macOS/Linux (bash):

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env              # add your GROQ_API_KEY
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --reload
```

Windows (PowerShell -- run one line at a time; PowerShell 5.1 doesn't
support `&&` as a statement separator):

```powershell
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env       # add your GROQ_API_KEY
cd frontend
npm install
npm run build
cd ..
uvicorn server:app --reload
```

Then open **http://localhost:8000**. Type domains into the form, click
**Run agent**, and cards fill in live as each domain finishes (the pipeline
still runs domains one at a time, so you'll see a "Processing" skeleton
card, then queued placeholders, resolve into real results). Reloading the
page always shows whatever the last run produced, via `GET /api/results`.

`server.py` wraps the exact same `graph.run_pipeline()` the CLI uses --
same agents, same 4-node LangGraph, same 1-call-per-domain LLM budget. It
just adds an HTTP layer (`POST /api/enrich`, `GET /api/enrich/{job_id}` for
polling, `GET /api/results`) and serves the built frontend from the same
process, so there's exactly one thing to start.

**Developing the frontend?** Run `uvicorn server:app --reload` in one
terminal and (`cd frontend`, then `npm run dev`) in another -- Vite's dev
server proxies `/api/*` to port 8000 (see `frontend/vite.config.js`), so
the app behaves identically to production.

## Proof, not just a spinner

Two things exist specifically so you're never just told to trust the
output:

- **Live activity log.** Both the CLI and the web app stream a line after
  every node finishes -- e.g. `Scraper: fetched homepage + 1 subpage(s)`,
  `Critique: verified 2 email(s) and 3 leader(s) against the scraped
  source -- nothing dropped`. In the browser this renders as a "Live
  activity" console under the run form. In the terminal it's the same
  messages through the normal logger. Source: `graph.stream_pipeline()`
  (see below) -- neither `main.py` nor `server.py` invents these messages,
  they just relay what each node actually returned.
- **Source text attached to every result.** `CompanyIntel.source_text`
  carries the exact cleaned text the Extractor Agent was given for that
  domain, so any claim (an email, a name, the overview) can be checked
  against it directly. The frontend exposes this as a "View scraped
  source" disclosure on each card, with a note on whether the Critique
  Agent found everything verifiable or had to drop something.

## Setup (CLI / scripted use)

Same `pip install` / `playwright install` / `.env` steps as above (see the
bash or PowerShell block in the previous section) -- then:

```bash
python main.py
```

   This runs the pipeline against the default test domains
   (`postman.com`, `supabase.com`, `vapi.ai`) and writes `output.json`.
   `server.py` (see above) will pick up this same file via `GET
   /api/results` next time it's running, no extra step needed.

   To run against your own domains instead:

   ```bash
   python main.py example.com another-company.com
   ```

This path exists for scripted/batch use and is what produced the sample
`output.json` committed in this repo. Day-to-day, the app in the section
above is the intended way to run it.

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
  "llm_calls_used": 1,
  "source_text": "--- Source: https://postman.com ---\n..."
}
```

`status` is one of `success`, `partial` (some fields missing), or `failed`
(scrape or extraction did not produce usable data -- see `error`).

## Project structure

```
main.py              CLI entry point: runs graph.py per domain, writes output.json
server.py             FastAPI app: runs graph.py from HTTP requests, serves frontend/dist
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
frontend/             Vite + React app (talks to server.py's API)
  src/App.jsx           Page layout, empty/loading/error states, run-level stats
  src/hooks/useEnrichment.js  Loads last results, submits runs, polls job status
  src/lib/api.js          Fetch wrappers for /api/*
  src/lib/format.js        Formatting + progress-merging helpers
  src/components/          Header, RunForm, ConsolePanel, StatsBar, ResultCard
                            (with the source-proof disclosure), PendingCard, StatusPill
```

## Notes on resilience

- Every network call (page navigation, LLM request) is wrapped in
  try/except; a failure is logged and the pipeline moves on.
- Subpage discovery is link-based (keyword-ranked `<a>` tags), so it
  degrades gracefully on sites with a different layout instead of hardcoding
  URL paths.
- Navigation retries once on transient failures before giving up (most
  real-world timeouts are a one-off network blip, not a hard block) --
  confirmed by testing against domains outside the 3 assignment demo
  targets (stripe.com, notion.so, linear.app, attio.com, zendesk.com).
- Same-site filtering for subpage discovery is based on where the homepage
  actually resolved to after redirects (`page.url`), not the URL as typed
  -- otherwise any domain that redirects to a different host (bare domain
  -> www, or a different registrable domain entirely, e.g. notion.so ->
  notion.com) would have every subpage silently discarded.
- The Critique Agent's email/name cross-check exists specifically to catch
  LLM hallucination -- it never trusts the model's output blindly, and the
  final confidence score is recomputed from actual evidence rather than
  taken as-is from the LLM.
- `main.py` catches any exception from a domain's graph run (not just the
  errors the nodes anticipate) so one bad domain can never crash the batch.
  `server.py`'s background job runner does the same per domain, so one bad
  domain in a browser-submitted run doesn't take the rest of that run down
  either.
- The frontend shows real loading/empty/error states: a skeleton
  "processing" card while a domain is in flight, an empty state before the
  first run, and an inline error banner (with a pointer to start the API
  server) if `/api/*` can't be reached.
