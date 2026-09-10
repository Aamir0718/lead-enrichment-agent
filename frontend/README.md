# Lead Enrichment Agent -- Frontend

Vite + React results viewer for the [Lead Enrichment Agent](../README.md)
pipeline. Renders `src/data/output.json` (kept in sync automatically by
`../main.py` after every pipeline run) as a light, premium results page.

## Stack

- **Vite** + **React** (JS, no TypeScript)
- **Tailwind CSS v4** (via `@tailwindcss/vite`) -- design tokens in
  `src/index.css`'s `@theme` block
- **Motion** (`motion/react`) for scroll-reveal on result cards
- **Phosphor Icons** (`@phosphor-icons/react`)
- Geist / Geist Mono via Google Fonts

## Run it

```bash
npm install
npm run dev
```

## Build it

```bash
npm run build     # -> dist/
npm run preview   # serves dist/ locally so you can view the production build
```

`dist/index.html` must be served (`npm run preview` or any static file
server), not opened directly via `file://` -- browsers block ES module
scripts on the `file://` origin. This applies to any Vite/webpack app, not
just this one.

## Structure

```
src/
  App.jsx              Page layout + run-level summary stats
  components/
    Header.jsx          Brand, Download JSON button, repo link
    StatsBar.jsx          Domains / success rate / avg confidence / LLM calls
    ResultCard.jsx         Per-domain card: overview, ICP, emails, leadership, pages, critique notes
    StatusPill.jsx          Success / partial / failed badge
  lib/format.js         Small formatting helpers (initials, bare URL, status meta)
  data/output.json      Synced copy of the pipeline's output.json
```
