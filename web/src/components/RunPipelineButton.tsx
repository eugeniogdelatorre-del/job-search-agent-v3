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

  async function handleClick() {
    if (uiState !== 'idle') return
    setUIState('queued')
    try {
      const res = await fetch('/api/pipeline/run', { method: 'POST' })
      const data = (await res.json()) as { runId: number | null; error?: string }
      if (!res.ok || data.error) {
        setUIState('failed')
        return
      }
      runIdRef.current = data.runId
      if (!data.runId) {
        // Run created but ID not yet available — keep polling anyway.
      }
      // Begin polling every 10 s.
      intervalRef.current = setInterval(pollStatus, 10_000)
    } catch {
      setUIState('failed')
    }
  }

  const isActive = uiState !== 'idle'
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
