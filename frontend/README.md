# Lead Enrichment Agent -- Frontend

Vite + React app for the [Lead Enrichment Agent](../README.md) pipeline.
Lets you enter company domains, run the pipeline, and watch structured
results appear live -- entirely from the browser, talking to
`../server.py`'s API (`/api/enrich`, `/api/enrich/{job_id}/stream` for
live Server-Sent-Events updates, `/api/results`).

## Stack

- **Vite** + **React** (JS, no TypeScript)
- **Tailwind CSS v4** (via `@tailwindcss/vite`) -- design tokens in
  `src/index.css`'s `@theme` block
- **Motion** (`motion/react`) for scroll-reveal on result cards
- **Phosphor Icons** (`@phosphor-icons/react`)
- Geist / Geist Mono via Google Fonts

## Run it

Needs `../server.py` running (`uvicorn server:app --reload` from the repo
root) for the API calls to resolve.

```bash
npm install
npm run dev        # Vite dev server, proxies /api/* to localhost:8000
```

## Build it

```bash
npm run build     # -> dist/, served by server.py in production
npm run preview   # serves dist/ locally to check the production build
```

`dist/index.html` must be served (`npm run preview`, `server.py`, or any
static file server), not opened directly via `file://` -- browsers block ES
module scripts on the `file://` origin. This applies to any Vite/webpack
app, not just this one.

## Structure

```
src/
  App.jsx              Page layout: run form, stats, results, empty/error states
  hooks/
    useEnrichment.js    Loads last results on mount, submits new runs, follows job
                          progress via Server-Sent Events
  lib/
    api.js               fetch wrappers for /api/enrich, /api/enrich/{id}, /api/results
    format.js             initials/URL helpers, status labels, progress-merging
  components/
    Header.jsx           Brand, Download JSON button, repo link
    RunForm.jsx            Domain input + Run button + inline validation
    StatsBar.jsx            Domains / success rate / avg confidence / LLM calls
    ResultCard.jsx           Per-domain card: overview, ICP, emails, leadership, pages, critique notes
    PendingCard.jsx           Skeleton card shown for a domain still processing/queued
    StatusPill.jsx            Success / partial / failed / processing / queued badge
```
