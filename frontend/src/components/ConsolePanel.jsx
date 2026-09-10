import { useEffect, useRef } from 'react'
import { TerminalWindow } from '@phosphor-icons/react'

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false })
}

/**
 * Live, timestamped trail of what the pipeline is actually doing -- the
 * same step-by-step log main.py prints to the terminal, surfaced here so a
 * browser-only user isn't just staring at a spinner with no evidence
 * anything is happening.
 */
export default function ConsolePanel({ logs, isRunning }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  if (logs.length === 0) return null

  return (
    <div className="mb-10 overflow-hidden rounded-[var(--radius-lg)] border border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border-soft bg-bg px-4 py-2.5">
        <TerminalWindow size={15} className="text-ink-faint" />
        <span className="text-xs font-medium text-ink-muted">Live activity</span>
        {isRunning && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-accent">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
            running
          </span>
        )}
      </div>
      <div ref={scrollRef} className="max-h-48 overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed">
        {logs.map((log, i) => (
          <div key={i} className="flex gap-3">
            <span className="flex-shrink-0 text-ink-faint">{formatTime(log.ts)}</span>
            <span className="text-ink-muted">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
