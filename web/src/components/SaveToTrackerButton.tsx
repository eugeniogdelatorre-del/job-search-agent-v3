'use client'

// Bookmark toggle — amber fill = saved, grey outline = not saved.
// Pass savedApplicationId (non-null) when the server already knows the job
// is saved. Clicking again calls DELETE to unsave.

import { useState } from 'react'
import { toast } from 'sonner'

type Props = {
  job_id:               string
  job_title_snapshot:   string
  company_snapshot:     string | null
  apply_url_snapshot:   string | null
  source_snapshot:      string | null
  savedApplicationId?:  string | null   // non-null = already in tracker
}

export function SaveToTrackerButton({
  savedApplicationId,
  ...saveProps
}: Props) {
  const [appId, setAppId] = useState<string | null>(savedApplicationId ?? null)
  const [busy,  setBusy]  = useState(false)

  async function toggle() {
    if (busy) return
    setBusy(true)
    try {
      if (appId) {
        // ── Unsave ──────────────────────────────────────────────
        const res = await fetch(`/api/applications?id=${appId}`, { method: 'DELETE' })
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string }
          throw new Error(body.error ?? 'delete failed')
        }
        setAppId(null)
        toast.success('Removed from tracker')
      } else {
        // ── Save ─────────────────────────────────────────────────
        const res = await fetch('/api/applications', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(saveProps),
        })
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string }
          throw new Error(body.error ?? 'save failed')
        }
        const data = (await res.json()) as {
          application: { id: string }
          duplicate?: boolean
        }
        setAppId(data.application.id)
        toast.success(data.duplicate ? 'Already in tracker' : 'Saved to tracker')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update tracker')
    } finally {
      setBusy(false)
    }
  }

  const isSaved = appId !== null

  return (
    <button
      onClick={toggle}
      disabled={busy}
      title={isSaved ? 'Remove from tracker' : 'Save to tracker'}
      className="flex items-center justify-center w-7 h-7 rounded transition-opacity duration-150"
      style={{ opacity: busy ? 0.5 : 1 }}
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
