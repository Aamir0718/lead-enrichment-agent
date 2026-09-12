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
       ▼                        │ retry already spent
  ┌─────────┐             ┌─────┴─────┐
  │ process │───────────▶│  extract   │◀────────┐
  └─────────┘             └──┬─────┬──┘          │
                     parsed ok│     │call/parse    │ retry
                              ▼     │failed        │
                        ┌──────────┐│              │
                        │ critique ││        ┌─────┴────┐
                        └───┬──┬───┘└───────▶│  retry   │
                       yes  │  │  no         └──────────┘
                            ▼  ▼
                          retry  (any leader missing a LinkedIn URL?)
                                    no │         │ yes
                                       ▼         ▼
                                 ┌──────────┐  ┌─────────────────┐
                                 │ finalize │◀─│ linkedin_search  │
                                 └──────────┘  └─────────────────┘
```

| Node | Agent | External call? | What it does |
|---|---|---|---|
| `scrape` | Scraper | No | Playwright: homepage + up to 4 relevant subpages (about/team/company/contact/pricing); flags pages that look like a bot-block/challenge response instead of real content |
| `process` | Processor | No | BeautifulSoup: strips scripts/styles/nav, produces clean bounded text + regex ground-truth **generic** emails only |
| `extract` | Extractor | **Yes, 1 LLM call** | Groq (`openai/gpt-oss-120b`): structured JSON extraction validated with Pydantic, tracks tokens + estimated cost |
| `critique` | Critique | No | Cross-checks emails/names against the Processor's generic-filtered ground truth to catch hallucinations, recomputes a grounded confidence score. Requests the retry back through `extract` if the result is unusable (both overview and ICP empty) |
| `retry` | - | No | Marks the one-time retry budget as spent, then loops back to `extract` |
| `linkedin_search` | LinkedIn Search (bonus) | Optional, up to 3 search calls | Only reached if a verified leader is still missing a LinkedIn URL. Searches via Tavily, no-ops cleanly with no `TAVILY_API_KEY` |
| `finalize` | Main | No | Aggregates node state into the final `CompanyIntel` record, including any scraper-level warnings |

The retry budget is spent at most once per domain, from whichever trigger
hits it first: an outright extraction failure (LLM call error, timeout, bad
JSON, schema validation) routes straight back to `retry`, since that's
usually a transient blip worth one more attempt; a *parsed-but-unusable*
result (valid JSON, empty overview/ICP) instead reaches Critique first,
which requests the retry with corrective feedback. Either way, a second
failure always falls through to `finalize` instead of looping again.

Worst case: 2 LLM calls per domain (retry) plus up to 3 LinkedIn search
calls (bonus feature, separate from the LLM budget). Typical case: 1 LLM
call, 0-3 LinkedIn searches only when needed. Every node's own external
calls are wrapped in try/except, and `main.py`/`server.py` wrap the whole
graph invocation per domain again -- a single domain's failure never stops
the batch. It's recorded with `status: "failed"` and an `error` message
instead.

The agent modules themselves (`agents/scraper.py`, `processor.py`,
`extractor.py`, `critique.py`, `linkedin_search.py`) are framework-agnostic
plain functions -- `graph.py` is a thin orchestration layer on top of them,
so the same functions could be re-wired into a different graph shape
without touching their internals.

### Concurrency and rate limits

Domains process concurrently (bounded by `MAX_CONCURRENT_DOMAINS`, default
3) in both the CLI and the API -- each domain gets its own Playwright
browser instance, so there's no shared state between them. This gives a
real speedup for the scraping stage.

The Extractor's actual LLM calls are paced separately
(`GROQ_MIN_SECONDS_BETWEEN_CALLS`, default 45s) regardless of how many
domains scrape concurrently. This exists because of a real finding, not a
theoretical one: testing 3 domains concurrently against Groq's free/
on-demand tier (8000 tokens-per-minute) produced repeated 429s and, once,
an outright failed domain -- a single ~5000-token extraction call already
uses most of that budget. Proactive pacing trades a bit of wall-clock time
for guaranteed reliability (no domain fails outright due to a rate-limit
collision), which matters more than raw speed for something meant to be
graded and rerun. On a paid Groq tier, lowering
`GROQ_MIN_SECONDS_BETWEEN_CALLS` lets concurrent scraping's benefit fully
show up in wall-clock time.

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
**Run agent**, and cards fill in live as domains finish -- since domains
run concurrently, more than one can show a "Processing" skeleton at once,
with "Queued" placeholders for the rest. Reloading the page always shows
whatever the last run produced, via `GET /api/results`.

`server.py` wraps the exact same `graph.stream_pipeline()` the CLI uses --
same agents, same LangGraph, same LLM budget. It adds an HTTP layer
(`POST /api/enrich` to start a run, `GET /api/enrich/{job_id}/stream` for
live Server-Sent-Events updates, `GET /api/results` for the last run) and
serves the built frontend from the same process, so there's exactly one
thing to start.

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

## Bonus features

- **Cost tracking.** Every result carries `prompt_tokens`,
  `completion_tokens`, `total_tokens`, and `estimated_cost_usd` (Groq's
  `response.usage`, priced via `GROQ_INPUT_COST_PER_1M` /
  `GROQ_OUTPUT_COST_PER_1M`). Shown per-domain on each card and totaled in
  the stats bar / run summary.
- **LinkedIn/founder search.** If a verified leader has no LinkedIn URL on
  the company's own site, `agents/linkedin_search.py` looks one up via
  Tavily (bounded to 3 lookups/domain), validated against a real
  `linkedin.com/in/...` URL pattern before being accepted -- never trusted
  blindly. Fully optional: no `TAVILY_API_KEY` means this step no-ops with
  a note, never an error.

## Setup (CLI / scripted use)

Same `pip install` / `playwright install` / `.env` steps as above (see the
bash or PowerShell block in the previous section) -- then:

```bash
python main.py
```

   This runs the pipeline against the default test domains
   (`postman.com`, `supabase.com`, `vapi.ai`) and writes both
   `output.json` (full fidelity) and `output.csv` (flattened,
   spreadsheet-friendly -- see `export.py`). `server.py` (see above) will
   pick up `output.json` via `GET /api/results` next time it's running, no
   extra step needed.

   To run against your own domains instead:

   ```bash
   python main.py example.com another-company.com
   ```

This path exists for scripted/batch use and is what produced the sample
`output.json`/`output.csv` committed in this repo. Day-to-day, the app in
the section above is the intended way to run it.

## Output format

Every run writes two files with the same records in different shapes --
`output.json` is the full-fidelity, primary format (nested leadership
objects, the exact scraped `source_text` each result was extracted from);
`output.csv` is a flattened, spreadsheet-friendly sibling of the same data
(list/object fields "; "-joined into single cells, `source_text` dropped
since a multi-thousand-character blob per row isn't useful in a
spreadsheet). Use whichever fits -- both are produced by the same run, not
by separate scripts.

`output.json` is a list of objects, one per domain:

```json
{
  "domain": "postman.com",
  "status": "success",
  "error": null,
  "company_overview": "...",
  "target_audience": "...",
  "contact_emails": ["help@postman.com"],
  "leadership": [
    {"name": "...", "role": "...", "linkedin_url": "https://www.linkedin.com/in/..."}
  ],
  "confidence_score": 0.92,
  "critique_notes": [],
  "pages_scraped": ["https://postman.com", "https://postman.com/company"],
  "llm_calls_used": 1,
  "linkedin_calls_used": 3,
  "prompt_tokens": 4491,
  "completion_tokens": 610,
  "total_tokens": 5101,
  "estimated_cost_usd": 0.00104,
  "source_text": "--- Source: https://postman.com ---\n..."
}
```

`status` is one of `success`, `partial` (some fields missing), or `failed`
(scrape or extraction did not produce usable data -- see `error`).

## Project structure

```
main.py              CLI entry point: runs domains concurrently via graph.py, writes output.json + output.csv
server.py             FastAPI app: runs graph.py from HTTP requests (+ SSE), serves frontend/dist
graph.py              LangGraph StateGraph wiring the five agents together
models.py             Pydantic schemas (ExtractionResult, CompanyIntel, TeamMember)
export.py             Flattens CompanyIntel results to CSV (output.csv)
agents/
  scraper.py          Scraper Agent -- Playwright, subpage discovery, bot-block detection, no LLM
  processor.py         Processor Agent -- HTML cleaning + generic-email regex, no LLM
  extractor.py         Extractor Agent -- the only LLM call in the normal path, tracks cost
  critique.py           Critique Agent -- deterministic hallucination/QA check
  linkedin_search.py     LinkedIn Search Agent (bonus) -- optional, Tavily-backed
requirements.txt
.env.example
output.json           Sample output (full fidelity) from a run against the 3 test domains
output.csv            Same sample run, flattened to CSV
tests/                pytest suite for the deterministic logic (no LLM/browser mocking needed)
  test_processor.py     Email filtering, HTML cleaning, text bounding
  test_critique.py       Hallucination detection, confidence scoring, retry decisions
  test_graph_routing.py    Pure routing functions + finalize_node aggregation
  test_scraper.py          URL normalization, same-site checks, link ranking, bot-block classification
  test_export.py           CSV flattening of leadership/list fields
frontend/             Vite + React app (talks to server.py's API)
  src/App.jsx           Page layout, empty/loading/error states, run-level stats
  src/hooks/useEnrichment.js  Loads last results, submits runs, follows SSE progress
  src/lib/api.js          Fetch wrappers for /api/*
  src/lib/format.js        Formatting + progress-merging helpers
  src/components/          Header, RunForm, ConsolePanel, StatsBar, ResultCard
                            (with the source-proof disclosure), PendingCard, StatusPill
```

## Running tests

```bash
pytest
```

60+ tests covering the deterministic agent logic and graph routing --
no LLM calls, no browser, no mocking needed since these are all pure
functions operating on plain data (scraper tests use a minimal fake
`page` object rather than launching Playwright).

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
- A page fetch that "succeeds" but actually lands on a bot-block/challenge
  page (Cloudflare, PerimeterX, etc.) is detected via status code and known
  page-content markers, not treated as real content -- the page is still
  kept (best-effort beats nothing) but flagged, and that flag surfaces all
  the way to the final result's `critique_notes`, not just the logs.
- An outright extraction failure (LLM API error, timeout, invalid JSON,
  schema validation) gets the same one-time retry budget as Critique's
  "result was empty" trigger -- a transient Groq hiccup doesn't
  permanently fail a domain that would have succeeded on a second try.
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
