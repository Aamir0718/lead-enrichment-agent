export function initials(name) {
  return (name || '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}

export function formatCost(usd) {
  if (!usd) return '$0.0000'
  return `$${usd.toFixed(4)}`
}

export function bareUrl(url) {
  return (url || '').replace(/^https?:\/\//, '').replace(/\/$/, '')
}

export function statusMeta(status) {
  if (status === 'success') return { label: 'Success', tone: 'success' }
  if (status === 'partial') return { label: 'Partial', tone: 'warning' }
  return { label: 'Failed', tone: 'danger' }
}

/**
 * Merges a job's submitted domain order with whatever results/in-progress
 * state have come back so far, so the UI can render a full-length list
 * immediately: real cards for completed domains, "Processing" for domains
 * the backend says are actively running, and "Queued" for the rest.
 *
 * Domains now run concurrently server-side (bounded by
 * MAX_CONCURRENT_DOMAINS), so more than one can be "Processing" at once --
 * this can no longer assume only the first pending domain is running.
 */
export function mergeProgress(domains, results, inProgress = []) {
  const byDomain = Object.fromEntries(results.map((r) => [r.domain, r]))
  const runningSet = new Set(inProgress)
  return domains.map((domain) => {
    const done = byDomain[domain]
    if (done) return done
    if (runningSet.has(domain)) {
      return { domain, pending: true, tone: 'processing', label: 'Processing' }
    }
    return { domain, pending: true, tone: 'queued', label: 'Queued' }
  })
}
