// Small client button that POSTs /api/applications with the snapshot
// fields from the current job row. Idempotent on job_id server-side,
// so double-clicking a bookmark is safe.

'use client'

import { useState } from 'react'
import { Bookmark, BookmarkCheck } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

type Props = {
  job_id: string
  job_title_snapshot: string
  company_snapshot: string | null
  apply_url_snapshot: string | null
  source_snapshot: string | null
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

  const Icon = state === 'saved' ? BookmarkCheck : Bookmark

  return (
    <Button
      variant="ghost"
      size="sm"
      title={state === 'saved' ? 'Saved' : 'Save to tracker'}
      disabled={state !== 'idle'}
      onClick={save}
    >
      <Icon className="h-4 w-4" />
    </Button>
  )
}
