'use client'

// Triggers the full scrape → classify → cv-score pipeline on click.
// Polls /api/pipeline/status every 10 s for live progress feedback.
// On success, shows a confirmation message for 10 s then resets to idle.

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'

type UIState =
  | 'idle'
  | 'queued'
  | 'scraping'
  | 'classifying'
  | 'scoring'
  | 'done'
  | 'failed'

const LABELS: Record<UIState, string> = {
  idle: '▶ Run Pipeline',
  queued: 'Queued…',
  scraping: 'Scraping all sources…',
  classifying: 'Classifying with Claude…',
  scoring: 'Scoring against your CV…',
  done: '✓ Done — refresh to see new jobs',
  failed: '✗ Failed — check GitHub Actions',
}

// Map the API's stage field to our UI state.
function stageToUIState(stage: string): UIState {
  if (stage === 'scrape') return 'scraping'
  if (stage === 'classify') return 'classifying'
  if (stage === 'cv-score') return 'scoring'
  if (stage === 'done') return 'done'
  if (stage === 'failed') return 'failed'
  // Audit L18: log unknown stages instead of silently returning
  // 'queued'. A new server-side stage value used to mask as "still
  // queued" forever — log so it shows up in browser console while we
  // continue degrading gracefully to 'queued'.
  console.warn('[RunPipelineButton] unknown stage value:', stage)
  return 'queued'
}

export function RunPipelineButton() {
  const [uiState, setUIState] = useState<UIState>('idle')
  const runIdRef = useRef<number | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clean up on unmount.
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      if (resetTimerRef.current) clearTimeout(resetTimerRef.current)
    }
  }, [])

  function stopPolling() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  async function pollStatus() {
    const runId = runIdRef.current
    if (!runId) return
    try {
      const res = await fetch(`/api/pipeline/status?runId=${runId}`)
      if (!res.ok) return
      const data = (await res.json()) as { stage: string }
      const next = stageToUIState(data.stage)
      setUIState(next)
      if (next === 'done' || next === 'failed') {
        stopPolling()
        if (next === 'done') {
          // Auto-reset to idle after 10 s.
          resetTimerRef.current = setTimeout(() => setUIState('idle'), 10_000)
        }
      }
    } catch {
      // Silently ignore transient network errors — will retry on next tick.
    }
  }

  // Allow re-click from 'failed' as well, so the user can retry without
  // waiting for the 10s reset. Audit L5.
  const canClick = uiState === 'idle' || uiState === 'failed'

  async function handleClick() {
    if (!canClick) return
    if (resetTimerRef.current) clearTimeout(resetTimerRef.current)
    setUIState('queued')
    try {
      const res = await fetch('/api/pipeline/run', { method: 'POST' })
      const data = (await res.json()) as { runId: number | null; error?: string }
      // Audit N-H7: a 409 ("pipeline already running") response carries
      // the runId of the run that's already in flight. Don't treat that
      // as a failure — adopt the existing runId and start polling.
      if (res.status === 409 && data.runId) {
        runIdRef.current = data.runId
        setUIState('queued')
        intervalRef.current = setInterval(pollStatus, 10_000)
        return
      }
      if (!res.ok || data.error) {
        setUIState('failed')
        // Auto-reset to idle after 10s so the user can retry without
        // refreshing — matches the success-path UX.
        resetTimerRef.current = setTimeout(() => setUIState('idle'), 10_000)
        return
      }
      // Audit H16: previously this proceeded to start an interval even
      // when runId was null. pollStatus() early-returns on falsy runId,
      // so the interval ticked forever doing nothing and the button
      // stayed disabled until the user refreshed. Treat null runId as a
      // failure so the user can retry.
      if (!data.runId) {
        setUIState('failed')
        resetTimerRef.current = setTimeout(() => setUIState('idle'), 10_000)
        return
      }
      runIdRef.current = data.runId
      // Begin polling every 10 s.
      intervalRef.current = setInterval(pollStatus, 10_000)
    } catch {
      setUIState('failed')
      resetTimerRef.current = setTimeout(() => setUIState('idle'), 10_000)
    }
  }

  const isActive = uiState !== 'idle' && uiState !== 'failed'
  const isDone = uiState === 'done'
  const isFailed = uiState === 'failed'

  return (
    <Button
      onClick={handleClick}
      disabled={isActive}
      variant={isDone ? 'default' : isFailed ? 'destructive' : 'outline'}
      size="sm"
      className="whitespace-nowrap"
    >
      {LABELS[uiState]}
    </Button>
  )
}
