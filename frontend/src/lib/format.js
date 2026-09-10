export function initials(name) {
  return (name || '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
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
 * Merges a job's submitted domain order with whatever results have come
 * back so far, so the UI can render a full-length list immediately: real
 * cards for completed domains, and live "processing" / "queued" placeholder
 * cards for the rest (the pipeline runs domains strictly in order, so at
 * most one is ever "processing" at a time).
 */
export function mergeProgress(domains, results) {
  const byDomain = Object.fromEntries(results.map((r) => [r.domain, r]))
  let processingAssigned = false
  return domains.map((domain) => {
    const done = byDomain[domain]
    if (done) return done
    if (!processingAssigned) {
      processingAssigned = true
      return { domain, pending: true, tone: 'processing', label: 'Processing' }
    }
    return { domain, pending: true, tone: 'queued', label: 'Queued' }
  })
}
