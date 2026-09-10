import { useCallback, useEffect, useRef, useState } from 'react'
import { getEnrichStatus, getLastResults, startEnrich } from '../lib/api'
import { mergeProgress } from '../lib/format'

const POLL_INTERVAL_MS = 1200

/**
 * Owns the whole "run the pipeline from the browser" lifecycle: loads the
 * last completed run on mount, submits new runs, and polls job status until
 * done -- merging in live "processing/queued" placeholders along the way so
 * the UI never just sits blank while the backend works.
 */
export function useEnrichment() {
  const [records, setRecords] = useState([])
  const [phase, setPhase] = useState('loading') // loading | idle | running | error
  const [error, setError] = useState(null)
  const [progress, setProgress] = useState(null)
  const [logs, setLogs] = useState([])
  const pollTimeoutRef = useRef(null)

  const stopPolling = useCallback(() => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
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
      stopPolling()
    }
  }, [stopPolling])

  const pollJob = useCallback((jobId, domains) => {
    getEnrichStatus(jobId)
      .then((data) => {
        setRecords(mergeProgress(domains, data.results))
        setProgress({ completed: data.completed, total: data.total })
        setLogs(data.logs || [])
        if (data.status === 'done') {
          setPhase('idle')
          setProgress(null)
        } else {
          pollTimeoutRef.current = setTimeout(() => pollJob(jobId, domains), POLL_INTERVAL_MS)
        }
      })
      .catch((err) => {
        setError(err.message)
        setPhase('error')
      })
  }, [])

  const submitDomains = useCallback(
    (domains) => {
      stopPolling()
      setError(null)
      setPhase('running')
      setProgress({ completed: 0, total: domains.length })
      setRecords(mergeProgress(domains, []))
      setLogs([])
      startEnrich(domains)
        .then((data) => pollJob(data.job_id, data.domains))
        .catch((err) => {
          setError(err.message)
          setPhase('error')
        })
    },
    [pollJob, stopPolling],
  )

  return { records, phase, error, progress, logs, submitDomains }
}
