import { useState } from 'react'
import { CircleNotch, PlayCircle } from '@phosphor-icons/react'

const MAX_DOMAINS = 10

function parseDomains(raw) {
  return Array.from(
    new Set(
      raw
        .split(/[\n,]/)
        .map((d) => d.trim())
        .filter(Boolean),
    ),
  )
}

export default function RunForm({ onSubmit, isRunning, progress }) {
  const [raw, setRaw] = useState('')
  const [validationError, setValidationError] = useState(null)

  function handleSubmit(event) {
    event.preventDefault()
    const domains = parseDomains(raw)
    if (domains.length === 0) {
      setValidationError('Enter at least one domain.')
      return
    }
    if (domains.length > MAX_DOMAINS) {
      setValidationError(`Up to ${MAX_DOMAINS} domains per run.`)
      return
    }
    setValidationError(null)
    onSubmit(domains)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mb-10 flex flex-col gap-3 rounded-[var(--radius-lg)] border border-border bg-surface p-6"
    >
      <div className="flex flex-col gap-2">
        <label htmlFor="domains" className="text-[11.5px] font-semibold tracking-wide text-ink-faint uppercase">
          Company domains
        </label>
        <textarea
          id="domains"
          rows={2}
          value={raw}
          onChange={(event) => setRaw(event.target.value)}
          disabled={isRunning}
          placeholder="postman.com, supabase.com, vapi.ai"
          className="w-full resize-none rounded-[var(--radius-md)] border border-border bg-bg px-3.5 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none disabled:opacity-60"
        />
        <span className="text-xs text-ink-faint">Comma or newline separated, up to {MAX_DOMAINS} domains.</span>
        {validationError && <span className="text-xs text-danger">{validationError}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={isRunning}
          className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isRunning ? <CircleNotch size={16} className="animate-spin" /> : <PlayCircle size={16} />}
          {isRunning ? 'Running...' : 'Run agent'}
        </button>
        {isRunning && progress && (
          <span className="text-sm text-ink-faint">
            Processing {progress.completed} of {progress.total} domain{progress.total === 1 ? '' : 's'}...
          </span>
        )}
      </div>
    </form>
  )
}
