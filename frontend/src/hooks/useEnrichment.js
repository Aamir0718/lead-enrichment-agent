import { useCallback, useEffect, useRef, useState } from 'react'
import { getLastResults, startEnrich } from '../lib/api'
import { mergeProgress } from '../lib/format'

/**
 * Owns the whole "run the pipeline from the browser" lifecycle: loads the
 * last completed run on mount, submits new runs, and follows job progress
 * via Server-Sent Events (server.py's /api/enrich/{id}/stream) -- pushing
 * updates the moment they happen rather than polling on a fixed interval.
 * Merges in live "processing/queued" placeholders along the way so the UI
 * never just sits blank while the backend works.
 */
export function useEnrichment() {
  const [records, setRecords] = useState([])
  const [phase, setPhase] = useState('loading') // loading | idle | running | error
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(null)
  const [logs, setLogs] = useState([])
  const eventSourceRef = useRef(null)

  const closeStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getLastResults()
      .then((data) => {
        if (cancelled) return
        setRecords(data)
        setPhase('idle')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setPhase('error')
      })
    return () => {
      cancelled = true
      closeStream()
    }
  }, [closeStream])

  const streamJob = useCallback(
    (jobId, domains) => {
      closeStream()
      const source = new EventSource(`/api/enrich/${jobId}/stream`)
      eventSourceRef.current = source

      source.onmessage = (event) => {
        const data = JSON.parse(event.data)
        setRecords(mergeProgress(domains, data.results, data.in_progress))
        setProgress({ completed: data.completed, total: data.total })
        setLogs(data.logs || [])
      }

      source.addEventListener('done', () => {
        setPhase('idle')
        setProgress(null)
        closeStream()
      })

      source.onerror = () => {
        // EventSource retries transient network hiccups on its own; only
        // surface a real error once the browser has given up entirely.
        if (source.readyState === EventSource.CLOSED) {
          setError('Lost connection to the enrichment stream')
          setPhase('error')
          closeStream()
        }
      }
    },
    [closeStream],
  )

  const submitDomains = useCallback(
    (domains) => {
      setError(null)
      setPhase('running')
      setProgress({ completed: 0, total: domains.length })
      setRecords(mergeProgress(domains, [], []))
      setLogs([])
      startEnrich(domains)
        .then((data) => streamJob(data.job_id, data.domains))
        .catch((err) => {
          setError(err.message)
          setPhase('error')
        })
    },
    [streamJob],
  )

  return { records, phase, error, progress, logs, submitDomains }
}
