'use client'

// Activate a specific resume. POSTs to /api/cv/activate, toasts,
// then refreshes so the server-rendered list picks up the flip.

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

export function ActivateResumeButton({ resumeId }: { resumeId: string }) {
  const router = useRouter()
  const [busy, setBusy] = useState(false)

  async function activate() {
    setBusy(true)
    try {
      const res = await fetch('/api/cv/activate', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ resume_id: resumeId }),
      })
      const json = await res.json()
      if (!res.ok) {
        toast.error(json.error || 'Activate failed')
        return
      }
      toast.success('Activated. Next CV scoring run uses this version.')
      router.refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Activate failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button variant="outline" size="sm" onClick={activate} disabled={busy}>
      {busy ? 'Activating…' : 'Activate'}
    </Button>
  )
}
