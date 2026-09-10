/**
 * Thin fetch wrappers around server.py's API. Relative paths only -- Vite's
 * dev proxy (see vite.config.js) forwards them to the API in development,
 * and server.py serves both the API and this built app from one origin in
 * production, so no base URL ever needs configuring.
 */

async function asJson(response) {
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail || (Array.isArray(body) ? null : null) || detail
    } catch {
      // response wasn't JSON -- fall back to statusText
    }
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export async function getLastResults() {
  const res = await fetch('/api/results')
  return asJson(res)
}

export async function startEnrich(domains) {
  const res = await fetch('/api/enrich', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ domains }),
  })
  return asJson(res)
}

export async function getEnrichStatus(jobId) {
  const res = await fetch(`/api/enrich/${jobId}`)
  return asJson(res)
}
