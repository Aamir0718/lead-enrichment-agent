import { useMemo } from 'react'
import Header from './components/Header'
import StatsBar from './components/StatsBar'
import ResultCard from './components/ResultCard'
import records from './data/output.json'

function downloadJson() {
  const blob = new Blob([JSON.stringify(records, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'output.json'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function App() {
  const stats = useMemo(() => {
    const total = records.length
    const succeeded = records.filter((r) => r.status === 'success').length
    const scored = records.filter((r) => typeof r.confidence_score === 'number')
    const avgConfidence = scored.length
      ? scored.reduce((sum, r) => sum + r.confidence_score, 0) / scored.length
      : 0
    const totalCalls = records.reduce((sum, r) => sum + (r.llm_calls_used || 0), 0)

    return [
      { label: 'Domains processed', value: total },
      { label: 'Success rate', value: total ? `${Math.round((succeeded / total) * 100)}%` : '-' },
      { label: 'Avg. confidence', value: avgConfidence.toFixed(2) },
      { label: 'Total LLM calls', value: totalCalls },
    ]
  }, [])

  return (
    <div className="min-h-dvh bg-bg text-ink">
      <Header onDownload={downloadJson} />

      <main className="mx-auto max-w-[1100px] px-6">
        <section className="max-w-[640px] py-12 pb-8">
          <h1 className="text-[clamp(28px,4vw,38px)] font-semibold tracking-tight text-ink">Extraction results</h1>
          <p className="mt-3 text-base leading-relaxed text-ink-muted">
            Structured company intelligence extracted from public web presence across{' '}
            <span className="font-medium text-ink">{records.length} target domains</span> by an autonomous,
            multi-agent pipeline.
          </p>
        </section>

        <StatsBar stats={stats} />

        <section aria-label="Per-domain results" className="flex flex-col gap-5 pb-16">
          {records.map((record, index) => (
            <ResultCard key={record.domain} record={record} index={index} />
          ))}
        </section>
      </main>

      <footer className="border-t border-border-soft">
        <div className="mx-auto max-w-[1100px] px-6 py-7">
          <p className="max-w-[640px] text-[13px] leading-relaxed text-ink-faint">
            Pipeline: Scraper &rarr; Processor &rarr; Extractor &rarr; Critique, orchestrated as a LangGraph state
            graph. The Scraper, Processor and Critique nodes run locally with no model calls; only the Extractor
            node calls an LLM, once per domain by default.
          </p>
        </div>
      </footer>
    </div>
  )
}
