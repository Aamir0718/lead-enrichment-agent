# Lead Enrichment Agent

A Python pipeline that takes a list of company domains, crawls their public
web presence with a headless browser, and uses an LLM to extract structured
company intelligence: overview, target audience/ICP, public contact emails,
leadership team, and a data confidence score.

## Architecture

The pipeline is split into four single-purpose agents coordinated by a main
orchestrator. Only the step that genuinely needs reasoning (extraction) calls
an LLM by default, to keep cost and latency minimal.

```
main.py (orchestrator)
  └─ for each domain:
       1. agents/scraper.py    Scraper Agent    (deterministic) Playwright:
                                homepage + up to 4 relevant subpages
                                (about/team/company/contact/pricing)
       2. agents/processor.py  Processor Agent  (deterministic) BeautifulSoup:
                                strips scripts/styles/nav, produces clean
                                bounded text + regex ground-truth emails
       3. agents/extractor.py  Extractor Agent  (1 LLM call)   Groq/Llama:
                                structured JSON extraction validated with Pydantic
       4. agents/critique.py   Critique Agent   (deterministic by default):
                                cross-checks emails/names against the actual
                                scraped text to catch hallucinations,
                                recomputes a grounded confidence score.
                                Triggers exactly ONE retry LLM call to the
                                Extractor only if the result is unusable
                                (both overview and ICP empty).
```

Worst case: 2 LLM calls per domain. Typical case: 1. Every stage is wrapped
so a single domain's failure (bot block, timeout, 404, malformed LLM output)
never stops the batch -- it's recorded with `status: "failed"` and an `error`
message instead.

## Setup

1. **Clone and install dependencies**

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
   (`postman.com`, `supabase.com`, `vapi.ai`) and writes `output.json`.

   To run against your own domains instead:

   ```bash
   python main.py example.com another-company.com
   ```

## Viewing results

`main.py` automatically generates `report.html` alongside `output.json` -- a
light, static results page (no server needed, just open it in a browser)
that shows each domain's extracted data as a readable card: overview, ICP,
contact emails, leadership, confidence score, and run-level stats. Safe to
re-run standalone any time output.json changes:

```bash
python generate_report.py
```

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
main.py              Orchestrator: runs the pipeline per domain, writes output.json
models.py             Pydantic schemas (ExtractionResult, CompanyIntel, TeamMember)
agents/
  scraper.py          Scraper Agent -- Playwright, subpage discovery, no LLM
  processor.py         Processor Agent -- HTML cleaning + email regex, no LLM
  extractor.py         Extractor Agent -- the only LLM call in the normal path
  critique.py           Critique Agent -- deterministic hallucination/QA check
generate_report.py    Renders output.json into report.html (no LLM)
requirements.txt
.env.example
output.json           Sample output from a run against the 3 test domains
report.html            Sample results page generated from output.json
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
