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
