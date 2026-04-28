'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

export function DeleteResumeButton({ resumeId }: { resumeId: string }) {
  const router = useRouter()
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    setDeleting(true)
    setConfirming(false)
    try {
      const res = await fetch('/api/cv/delete', {
        method: 'DELETE',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ resume_id: resumeId }),
      })
      const json = await res.json()
      if (!res.ok) {
        toast.error(json.error ?? 'Delete failed')
        return
      }
      toast.success('CV deleted')
      router.refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  if (deleting) {
    return (
      <span className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
        Deleting…
      </span>
    )
  }

  if (confirming) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[10px]" style={{ color: '#A0AABB' }}>
          Sure?
        </span>
        <button
          onClick={handleDelete}
          className="font-mono text-[10px] rounded-[5px] px-2.5 py-1"
          style={{
            background: 'rgba(252,165,165,0.08)',
            border: '1px solid rgba(252,165,165,0.35)',
            color: '#FCA5A5',
          }}
        >
          Yes, delete
        </button>
        <button
          onClick={() => setConfirming(false)}
          className="font-mono text-[10px] rounded-[5px] px-2.5 py-1"
          style={{
            background: 'transparent',
            border: '1px solid #252D40',
            color: '#6B7A99',
          }}
        >
          Cancel
        </button>
      </div>
    )
  }

  return (
    <button
      onClick={() => setConfirming(true)}
      className="font-mono text-[10px] rounded-[5px] px-2.5 py-1 transition-colors"
      style={{
        background: 'transparent',
        border: '1px solid #252D40',
        color: '#3A4460',
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(252,165,165,0.4)'
        ;(e.currentTarget as HTMLElement).style.color = '#FCA5A5'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLElement).style.borderColor = '#252D40'
        ;(e.currentTarget as HTMLElement).style.color = '#3A4460'
      }}
    >
      delete
    </button>
  )
}
