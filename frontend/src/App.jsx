import { useMemo } from 'react'
import { Tray, WarningCircle } from '@phosphor-icons/react'
import Header from './components/Header'
import RunForm from './components/RunForm'
import ConsolePanel from './components/ConsolePanel'
import StatsBar from './components/StatsBar'
import ResultCard from './components/ResultCard'
import { useEnrichment } from './hooks/useEnrichment'

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-[var(--radius-lg)] border border-dashed border-border py-16 text-center">
      <Tray size={28} className="text-ink-faint" />
      <p className="text-sm text-ink-muted">No results yet. Enter domains above and run the agent.</p>
    </div>
  )
}

function ErrorBanner({ message }) {
  return (
    <div className="mb-10 flex items-center gap-2.5 rounded-[var(--radius-md)] border border-danger/20 bg-danger-soft px-4 py-3 text-sm text-danger">
      <WarningCircle size={18} className="flex-shrink-0" />
      <span>
        {message}. Make sure the API server is running (<code className="font-mono">uvicorn server:app --reload</code>).
      </span>
    </div>
  )
}

export default function App() {
  const { records, phase, error, progress, logs, submitDomains } = useEnrichment()

  const completed = useMemo(() => records.filter((r) => !r.pending), [records])

  const stats = useMemo(() => {
    const total = completed.length
    const succeeded = completed.filter((r) => r.status === 'success').length
    const scored = completed.filter((r) => typeof r.confidence_score === 'number')
    const avgConfidence = scored.length
      ? scored.reduce((sum, r) => sum + r.confidence_score, 0) / scored.length
      : 0
    const totalCalls = completed.reduce((sum, r) => sum + (r.llm_calls_used || 0), 0)

    return [
      { label: 'Domains processed', value: total },
      { label: 'Success rate', value: total ? `${Math.round((succeeded / total) * 100)}%` : '-' },
      { label: 'Avg. confidence', value: avgConfidence.toFixed(2) },
      { label: 'Total LLM calls', value: totalCalls },
    ]
  }, [completed])

  function downloadJson() {
    const blob = new Blob([JSON.stringify(completed, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'output.json'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-dvh bg-bg text-ink">
      <Header onDownload={downloadJson} downloadDisabled={completed.length === 0 || phase === 'running'} />

      <main className="mx-auto max-w-[1100px] px-6">
        <section className="max-w-[640px] py-12 pb-8">
          <h1 className="text-[clamp(28px,4vw,38px)] font-semibold tracking-tight text-ink">Extraction results</h1>
          <p className="mt-3 text-base leading-relaxed text-ink-muted">
            Enter company domains below to run the autonomous, multi-agent pipeline and see structured company
            intelligence appear live, right here in the browser.
          </p>
        </section>

        <RunForm onSubmit={submitDomains} isRunning={phase === 'running'} progress={progress} />

        <ConsolePanel logs={logs} isRunning={phase === 'running'} />

        {phase === 'error' && <ErrorBanner message={error} />}

        {completed.length > 0 && <StatsBar stats={stats} />}

        <section aria-label="Per-domain results" className="flex flex-col gap-5 pb-16">
          {records.length > 0 ? (
            records.map((record, index) => <ResultCard key={record.domain} record={record} index={index} />)
          ) : phase === 'idle' ? (
            <EmptyState />
          ) : null}
        </section>
      </main>

      <footer className="border-t border-border-soft">
        <div className="mx-auto max-w-[1100px] px-6 py-7">
          <p className="max-w-[640px] text-[13px] leading-relaxed text-ink-faint">
            Pipeline: Scraper &rarr; Processor &rarr; Extractor &rarr; Critique, orchestrated as a LangGraph state
            graph and run from this page via server.py. The Scraper, Processor and Critique nodes run locally with
            no model calls; only the Extractor node calls an LLM, once per domain by default.
          </p>
        </div>
      </footer>
    </div>
  )
}
