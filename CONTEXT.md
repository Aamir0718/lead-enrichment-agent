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
