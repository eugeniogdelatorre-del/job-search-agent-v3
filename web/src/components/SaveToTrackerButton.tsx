'use client'

// Bookmark button — fills amber when the job is saved to the tracker.
// POSTs /api/applications; idempotent on job_id server-side.

import { useState } from 'react'
import { toast } from 'sonner'

type Props = {
  job_id:                string
  job_title_snapshot:    string
  company_snapshot:      string | null
  apply_url_snapshot:    string | null
  source_snapshot:       string | null
}

export function SaveToTrackerButton(props: Props) {
  const [state, setState] = useState<'idle' | 'saving' | 'saved'>('idle')

  async function save() {
    if (state !== 'idle') return
    setState('saving')
    try {
      const res = await fetch('/api/applications', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(props),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string }
        throw new Error(body.error ?? 'save failed')
      }
      const data = (await res.json()) as { duplicate?: boolean }
      setState('saved')
      toast.success(data.duplicate ? 'Already in tracker' : 'Saved to tracker')
    } catch (e) {
      setState('idle')
      toast.error(e instanceof Error ? e.message : 'Could not save')
    }
  }

  const isSaved = state === 'saved'

  return (
    <button
      onClick={save}
      disabled={state === 'saving'}
      title={isSaved ? 'Saved' : 'Save to tracker'}
      className="flex items-center justify-center w-7 h-7 rounded transition-opacity duration-150"
      style={{ opacity: state === 'saving' ? 0.5 : 1 }}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill={isSaved ? '#F5A623' : 'none'}
        stroke={isSaved ? '#F5A623' : '#6B7A99'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
      </svg>
    </button>
  )
}
