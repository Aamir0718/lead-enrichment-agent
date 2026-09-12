# Project Context

## What this is
Take-home assignment for SoftwareBrio AI Engineer Intern role.
Build a Python pipeline that takes company domains, scrapes their public site,
and uses an LLM to extract structured company intel (overview, ICP, contact
emails, leadership, confidence score).

Test domains: postman.com, supabase.com, vapi.ai

## Architecture decision
Multi-agent pipeline, orchestrated by a main agent, but LLM calls kept to a
strict minimum for cost reasons:

1. **Scraper Agent** (deterministic, no LLM) — Playwright headless browser.
   Fetches homepage, discovers + visits candidate subpages (about/team/company/
   contact/pricing), handles timeouts/404/bot-blocks without crashing.
2. **Processor Agent** (deterministic, no LLM) — BeautifulSoup. Strips
   script/style/svg/nav boilerplate, converts to clean text, regex-extracts
   raw emails as a ground-truth cross-check.
3. **Extractor Agent** (1 LLM call per domain) — Groq (Llama), structured
   JSON output validated against a Pydantic schema.
4. **Critique Agent** (deterministic, no LLM by default) — cross-checks
   extractor's emails/names against the scraped source text to catch
   hallucinations, recomputes confidence score. Triggers exactly ONE retry
   LLM call to the Extractor only if the first output badly fails validation
   (bad JSON / zero usable fields).
5. **Main Agent** — orchestrates all of the above per domain, aggregates
   results, writes output.json, never crashes on a single domain failure.

Worst case: 2 LLM calls/domain. Typical: 1. Total for 3 domains: 3-6 calls.

**Update:** orchestration (step 5, and the control flow linking 1-4) is now
implemented as a LangGraph `StateGraph` (see `graph.py`) instead of plain
Python if/else -- same 5-agent architecture, same LLM-call budget, just a
real graph with conditional edges for the retry loop. See Status below.

## Provider
Groq (free/cheap tier) — user will supply GROQ_API_KEY in .env.

## Constraints / house rules for this repo
- No "Claude Code" / AI-tool attribution anywhere in git commits or code
  comments. User will submit this as their own work for an internship
  application.
- Keep this CONTEXT.md updated as the project progresses (status, decisions,
  what's left).

## Status
- [x] Repo scaffolded, git initialized
- [x] models.py (Pydantic schema)
- [x] agents/scraper.py
- [x] agents/processor.py
- [x] agents/extractor.py
- [x] agents/critique.py
- [x] main.py orchestrator
- [x] requirements.txt / .env.example / .gitignore
- [x] README.md
- [x] Run against 3 test domains, produce output.json (all 3: status=success,
      3 total LLM calls, 0 retries needed, 0 hallucinations flagged by critique)
- [x] Pushed to GitHub: https://github.com/Aamir0718/lead-enrichment-agent
- [x] Added generate_report.py -> report.html (static HTML results page).
      SUPERSEDED -- removed once the React frontend shipped (see below).
- [x] Refactored orchestration onto LangGraph (user request, forgot to
      mention at the start): new graph.py builds a LangGraph StateGraph
      wiring the same four agents (scrape -> process -> extract -> critique,
      with a conditional retry edge back to extract). agents/*.py unchanged
      -- same architecture, just a real graph instead of hand-rolled
      if/else in main.py. Verified: same 1-call-typical / 2-call-worst-case
      LLM budget, all 3 domains still succeed.
- [x] Replaced report.html with a proper React frontend (user request):
      frontend/ is a Vite + React app (Tailwind v4 via @tailwindcss/vite,
      Motion for scroll-reveal, @phosphor-icons/react, Geist/Geist Mono).
      Same visual design as the old static report (light theme, cobalt
      accent, card layout, Download JSON button) but componentized
      (Header/StatsBar/ResultCard/StatusPill). main.py syncs output.json
      into frontend/src/data/output.json after every run.
      Verified via Playwright against `npm run preview` (production build
      won't run off file:// -- ES module CORS restriction in all browsers,
      not a bug -- documented in both READMEs): 3 cards render, 0 console
      errors, download button produces a real 3-record output.json.
- [x] Updated root README.md and frontend/README.md for both changes.
- [x] Turned it into a real app (user request: "no terminal needed except
      to start it, should be like an application"): new server.py (FastAPI)
      wraps graph.run_pipeline() behind POST /api/enrich (starts a
      background-thread job), GET /api/enrich/{job_id} (poll, returns
      results incrementally as each domain finishes), GET /api/results
      (last completed run), and serves frontend/dist as static files so one
      `uvicorn server:app` process is the whole product.
      Frontend: added RunForm (domain textarea + Run button), useEnrichment
      hook (loads last results on mount, submits runs, polls every 1.2s),
      PendingCard (skeleton with animated "Processing"/"Queued" status pill
      for domains not yet done -- pipeline runs domains in order so at most
      one is ever "Processing"), empty state, and an error banner if the
      API can't be reached. Removed frontend/src/data/output.json (static
      bundled copy) and main.py's sync step -- no longer needed now that
      the frontend fetches live from the API.
      Verified via Playwright against the real server (not just the build):
      loaded last run's 3 results on page load, submitted a live 1-domain
      run through the actual UI, watched the processing skeleton appear,
      confirmed it resolved to a correct real result card with stats
      updating -- 0 console errors throughout. Re-ran the CLI afterward to
      restore the full 3-domain output.json (the live UI test had
      overwritten it with a 1-domain run).
- [x] Added proof/verifiability (user request: "I should be able to see
      what's actually happening... how do we know the data is right"):
      - graph.py: new `_describe_step()` + `stream_pipeline()` generator,
        using LangGraph's `.stream(mode="updates")` instead of `.invoke()`
        so a human-readable log line is emitted after every node
        (`Scraper: fetched homepage + 1 subpage(s)`, `Critique: verified 2
        email(s) and 3 leader(s) against the scraped source`, etc).
        `run_pipeline()` kept as a thin wrapper for simple callers.
      - models.py: CompanyIntel gained `source_text` -- the exact cleaned
        text the Extractor saw, carried through to output.json as
        evidence every field can be checked against.
      - main.py: CLI now logs every step line (not just start/done).
      - server.py: Job gained a `logs` list, appended to during
        `_execute_job`, returned from `GET /api/enrich/{job_id}` alongside
        results.
      - frontend: new ConsolePanel.jsx (timestamped, auto-scrolling, shown
        while a job has any logs) and a SourceProof block inside
        ResultCard.jsx (verification note + collapsible raw source text).
      Verified against the real running server (not just the build): the
      live-run screenshot shows the console filling in with real per-node
      lines and the expanded source panel showing actual scraped vapi.ai
      text, zero console errors.
- [x] Generalized beyond the 3 demo domains (user asked: "it works for 3
      domains but not others -- can we improve, or is that against the
      requirement?" -- answer: improving it is exactly what the rubric
      wants, the 3 domains are just the demo set). Tested against 5 domains
      outside the assignment's set (stripe.com, notion.so, linear.app,
      attio.com, zendesk.com) before changing anything -- 4/5 worked
      immediately, notion.so failed with a clean timeout (no crash, matches
      the "never crash" design goal already). Root-caused before fixing:
      a fresh direct test showed notion.so loads fine in 3.7s (redirects to
      notion.com), so it was a transient blip, not a real block.
      Two agents/scraper.py fixes, both re-verified after: (1) navigation
      now retries once on transient failures (`_goto_with_retry`,
      NAV_TIMEOUT_MS 15s->20s); (2) same-site subpage filtering now uses
      `page.url` (where the homepage actually resolved to after redirects)
      instead of the typed URL -- previously any domain that redirects to
      a different host (bare domain -> www, or a different registrable
      domain entirely like notion.so -> notion.com) had every subpage
      silently discarded, since the host comparison never matched. Re-ran
      notion.so after the fix: 5 correctly-resolved pages, 0 errors.
      Re-ran the 3 required domains afterward: no regression, still 1 LLM
      call each, all success.
- [ ] User records Loom walkthrough (their side)
- [ ] Submit email to support@softwarebrio.com

## Known environment quirk (not a project bug)
During testing, an earlier accidental `uvicorn server:app` invocation (the
backtick/command-substitution incident, now fixed) left a stray process
holding port 8000 that this sandboxed session's Get-Process/taskkill can't
see or kill (though `netstat -ano` confirms it's still there). Worked
around by testing on port 8001. If the user hits "address already in use"
on port 8000 themselves, it's likely this leftover -- closing the terminal
it came from, restarting their machine, or finding it in Task Manager
(outside this sandbox they have full access) will clear it; `uvicorn
server:app --reload --port 8001` (or any other port) is a fine workaround
either way.

## Notes / gotchas hit during build
- Groq SDK 0.11.0 is incompatible with httpx>=0.28 (`proxies` kwarg error).
  Fixed by upgrading to groq==1.7.0.
- `llama-3.3-70b-versatile` is retired on Groq's current catalog for this
  key. Switched default model to `openai/gpt-oss-120b` (set via GROQ_MODEL
  env var, overridable).
- Windows console (cp1252) can crash on unicode in scraped text when
  printed; main.py reconfigures stdout/stderr to utf-8 on startup.

## Sample run result (3 test domains)
| domain | status | confidence | emails | leadership | llm_calls |
|---|---|---|---|---|---|
| postman.com | success | 0.92 | 1 | 3 | 1 |
| supabase.com | success | 0.50 | 0 | 0 | 1 |
| vapi.ai | success | 0.66 | 0 | 1 | 1 |

## Architecture review + 4-workstream expansion (2026-09-12)
User asked "is this the best architecture, or can there be better?" --
answered honestly: a repo survey found the design solid for the assignment,
but with 5 concrete gaps, not just style nitpicks. User selected all 4
proposed improvement tracks (a 5th, job persistence via SQLite, was
explicitly NOT recommended -- over-engineering for a local single-user
demo). Order chosen to minimize rework: shared-file changes first,
structural changes last.

**Workstream 1 -- email filtering + cost tracking:**
- `agents/processor.py`: `extract_emails()` now actually uses
  `GENERIC_PREFIXES` (was defined but unused before) -- only surfaces
  contact@/sales@/support@-style addresses, matching the assignment's
  literal spec ("generic or public emails"). Added `"help"` to the
  prefix list after real data (`help@postman.com`) would otherwise have
  been dropped.
- `agents/critique.py`: email verification now checks membership in the
  Processor's already-generic-filtered `raw_emails_found` (passed through
  `graph.py`'s state) instead of a bare substring search -- simpler and
  actually enforces "generic," not just "present." New resilience
  behavior: if the LLM reports zero emails but the regex scan found real
  generic ones, they're surfaced anyway with a note (never let a
  trivially-detectable fact go unreported just because the model missed
  it). Fixed a knock-on bug in the confidence-score math: the old
  `len(a) - len(b)` dropped-count calculation could go negative once the
  fallback could make the "verified" list longer than what was claimed.
- `agents/extractor.py`: captures `response.usage` from Groq, added a
  `TokenUsage` dataclass with `prompt_tokens`/`completion_tokens`/
  `total_tokens`/`estimated_cost_usd`. Pricing ($0.15/$0.60 per 1M input/
  output tokens for `openai/gpt-oss-120b`) looked up from
  console.groq.com's own docs via WebSearch, not guessed -- overridable
  via env vars, documented as an estimate.
- `models.py` + `graph.py`: `CompanyIntel` and `PipelineState` carry the
  new token/cost fields through `extract_node` -> `finalize_node`.
- Frontend: `ResultCard.jsx` shows tokens + cost per domain,
  `StatsBar.jsx`/`App.jsx` show a 5th "Est. total cost" stat.
- Verified: `help@postman.com` still survives the new filter; token/cost
  fields populate correctly (5,101 tokens / $0.00104 for a real postman.com
  run); all 3 required domains still succeed at 1 LLM call each.

**Workstream 2 -- pytest suite:**
- New `tests/` (40+ tests): `test_processor.py`, `test_critique.py`,
  `test_graph_routing.py` -- all pure functions, no LLM/browser mocking.
  Two tests initially failed on first run, both because the test's
  *assumption* was wrong, not the code: one didn't account for the new
  fallback-to-regex-emails behavior masking a hallucination-drop it meant
  to isolate; the other didn't realize reporting zero emails/leadership
  already carries a small penalty regardless of drops. Fixed by adjusting
  the test setup, not the production code. `pytest==9.1.1` added to
  requirements.txt.

**Workstream 3 -- concurrency + real-time streaming:**
- `main.py` and `server.py`: domains now run concurrently via
  `ThreadPoolExecutor` (bounded by `MAX_CONCURRENT_DOMAINS`, default 3)
  instead of a sequential loop -- safe because each domain gets its own
  Playwright browser instance already.
- **Real finding from testing, not theoretical**: running 3 domains
  concurrently against Groq's free/on-demand tier (8000 TPM) produced
  repeated 429s and one outright failed domain (supabase.com), because a
  single ~5000-token extraction call already uses most of that budget.
  Fixed with a proactive pacing gate in `agents/extractor.py`
  (`_throttle_llm_call`, `GROQ_MIN_SECONDS_BETWEEN_CALLS=45` default) --
  strictly better than relying on reactive SDK retry-backoff, which was
  costing 30+ seconds per collision anyway. Documented the honest
  trade-off: for a small batch (<= MAX_CONCURRENT_DOMAINS) this makes
  wall-clock time consistent (~130s for 3 domains) rather than
  occasionally-fast-but-flaky; the real throughput ceiling is Groq's
  free-tier TPM, not the architecture -- a paid tier would let concurrent
  scraping's benefit fully show up.
- `server.py`: `Job` gained `in_progress: set[str]` (more than one domain
  can now be actively running, so the frontend can't assume "only the
  first pending domain is running" anymore). New
  `GET /api/enrich/{job_id}/stream` (SSE) pushes updates the moment
  anything changes instead of the client polling every 1.2s -- honestly
  documented as an internal short-poll-turned-push, not a full pub/sub
  rewrite (would be over-engineering here).
- Frontend: `lib/format.js`'s `mergeProgress()` now takes an `inProgress`
  list and marks any domain in it "Processing" (was: only the first
  pending domain). `useEnrichment.js` rewritten to use `EventSource`
  instead of a `setTimeout` poll loop.
- Verified end-to-end via Playwright against the real running server (not
  just the build): submitted 2 domains, confirmed BOTH showed "Processing"
  simultaneously with identical timestamps in the live console (proof of
  real concurrency, not sequential), zero console errors, correct final
  stats. (One false alarm during this test: a screenshot taken without
  scrolling first showed an apparently-empty page with what looked like a
  duplicate footer -- this was the same `whileInView` Motion animation
  needing the viewport to actually scroll past a card before it reveals,
  same as an earlier false alarm in this project; re-confirmed by checking
  `article` element count in the DOM (2, correct) and re-screenshotting
  after scrolling through, which rendered correctly.)

**Workstream 4 -- LinkedIn/founder search (bonus):**
- New `agents/linkedin_search.py`: `find_linkedin_url(name, domain)` via
  Tavily (`tavily-python==0.8.2`), validates the result actually matches
  `linkedin.com/in/...` before accepting it (same "verify, don't trust"
  principle as Critique) -- never raises, returns `None` cleanly with no
  `TAVILY_API_KEY` configured.
- `graph.py`: new `linkedin_search` node, reached only when critique isn't
  retrying AND at least one verified leader is still missing a LinkedIn
  URL (`route_after_critique` extended to 3 branches); bounded to 3
  lookups/domain; adds a transparency note per URL found ("via web search,
  not present on the scraped pages"), and a skip-note when no API key is
  configured. `CompanyIntel.linkedin_calls_used` added.
- User provided a real `TAVILY_API_KEY` (in `.env`, gitignored, never
  committed) for end-to-end verification -- not just unit-tested.
- Verified: vapi.ai's Jason Mitura (previously `linkedin_url: null`) ->
  found `https://www.linkedin.com/in/jasonmitura`, a real, correctly-
  formatted profile URL. Re-ran the 3 required domains afterward: Postman
  found real LinkedIn URLs for 2 of its 3 co-founders (Abhinav Asthana,
  Ankit Sobti; Abhijit Kane's wasn't found, correctly returned as `None`
  rather than a guess). Also independently verified the no-key no-op path
  returns `linkedin_calls_used: 0` with a clean skip note, no error.

**Docs**: README.md (architecture diagram/table, concurrency + rate-limit
section, "Bonus features" section, output format example, project
structure, "Running tests"), frontend/README.md (SSE mention), this file,
and `.env.example` all updated to match.
