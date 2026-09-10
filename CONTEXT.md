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
- [x] Added generate_report.py -> report.html: light, premium static results
      page (Geist/Geist Mono via Google Fonts, Phosphor icons, single cobalt
      accent, no dark mode by explicit user request). Auto-runs at the end
      of main.py; also runnable standalone. Verified visually via Playwright
      screenshots at desktop (1280px) and mobile (390px) widths -- responsive,
      cards render correctly, scroll-reveal animation works as intended.
- [ ] User records Loom walkthrough (their side)
- [ ] Submit email to support@softwarebrio.com

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
