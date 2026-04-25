'use client'

// Two exports:
//
//   ActivateResumeButton — shown on *inactive* CV rows.
//     "Activate"            → /api/cv/activate  (activate only, no rescore)
//     "Activate & re-score" → /api/cv/rescore   (activate + dispatch workflow)
//
//   RescoreButton — shown on the *active* CV row.
//     "Re-score now"        → /api/cv/rescore   (dispatch without activating)
//
// Both toast a descriptive error if GITHUB_PAT is not yet configured.

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

// ── Shared style helpers ──────────────────────────────────────────────────────

const BTN_BASE: React.CSSProperties = {
  fontFamily:   'var(--font-mono)',
  fontSize:     '10px',
  fontWeight:   500,
  borderRadius: '5px',
  padding:      '5px 10px',
  height:       '26px',
  cursor:       'pointer',
  border:       '1px solid transparent',
  transition:   'background 0.15s, border-color 0.15s, color 0.15s',
  whiteSpace:   'nowrap',
}

const BTN_OUTLINE: React.CSSProperties = {
  ...BTN_BASE,
  background:   'transparent',
  borderColor:  '#252D40',
  color:        '#6B7A99',
}

const BTN_CYAN: React.CSSProperties = {
  ...BTN_BASE,
  background:   'rgba(0,212,255,0.10)',
  borderColor:  'rgba(0,212,255,0.35)',
  color:        '#00D4FF',
}

// ── ActivateResumeButton ──────────────────────────────────────────────────────

export function ActivateResumeButton({ resumeId }: { resumeId: string }) {
  const router = useRouter()
  const [activating, setActivating] = useState(false)
  const [rescoring,  setRescoring]  = useState(false)

  async function activate() {
    if (activating || rescoring) return
    setActivating(true)
    try {
      const res  = await fetch('/api/cv/activate', {
        method:  'POST',
        headers: { 'content-type': 'application/json' },
        body:    JSON.stringify({ resume_id: resumeId }),
      })
      const json = (await res.json()) as { error?: string }
      if (!res.ok) { toast.error(json.error ?? 'Activate failed'); return }
      toast.success('Activated — next nightly run scores against this CV.')
      router.refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Activate failed')
    } finally {
      setActivating(false)
    }
  }

  async function activateAndRescore() {
    if (activating || rescoring) return
    setRescoring(true)
    try {
      const res  = await fetch('/api/cv/rescore', {
        method:  'POST',
        headers: { 'content-type': 'application/json' },
        body:    JSON.stringify({ resume_id: resumeId }),
      })
      const json = (await res.json()) as { error?: string; message?: string }
      if (!res.ok) { toast.error(json.error ?? 'Request failed'); return }
      toast.success(json.message ?? 'CV activated and re-score queued')
      router.refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setRescoring(false)
    }
  }

  const busy = activating || rescoring

  return (
    <div className="flex items-center gap-1.5">
      {/* Plain activate — for when you just want to switch without burning a run */}
      <button
        onClick={activate}
        disabled={busy}
        style={{ ...BTN_OUTLINE, opacity: busy ? 0.5 : 1 }}
        onMouseEnter={(e) => {
          if (!busy) {
            ;(e.currentTarget as HTMLElement).style.borderColor = '#6B7A99'
            ;(e.currentTarget as HTMLElement).style.color       = '#E8ECF0'
          }
        }}
        onMouseLeave={(e) => {
          ;(e.currentTarget as HTMLElement).style.borderColor = '#252D40'
          ;(e.currentTarget as HTMLElement).style.color       = '#6B7A99'
        }}
      >
        {activating ? 'Activating…' : 'Activate'}
      </button>

      {/* Primary: activate + immediately kick off scoring */}
      <button
        onClick={activateAndRescore}
        disabled={busy}
        style={{ ...BTN_CYAN, opacity: busy ? 0.5 : 1 }}
        onMouseEnter={(e) => {
          if (!busy) {
            ;(e.currentTarget as HTMLElement).style.background  = 'rgba(0,212,255,0.18)'
            ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.6)'
          }
        }}
        onMouseLeave={(e) => {
          ;(e.currentTarget as HTMLElement).style.background  = 'rgba(0,212,255,0.10)'
          ;(e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,212,255,0.35)'
        }}
      >
        {rescoring ? 'Queuing…' : 'Activate & re-score'}
      </button>
    </div>
  )
}

// ── RescoreButton — active CV row ─────────────────────────────────────────────

export function RescoreButton() {
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  async function rescore() {
    if (busy || done) return
    setBusy(true)
    try {
      const res  = await fetch('/api/cv/rescore', { method: 'POST' })
      const json = (await res.json()) as { error?: string; message?: string }
      if (!res.ok) { toast.error(json.error ?? 'Request failed'); return }
      toast.success(json.message ?? 'Re-score queued')
      setDone(true)
      setTimeout(() => setDone(false), 4000)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      onClick={rescore}
      disabled={busy}
      style={{
        ...BTN_OUTLINE,
        opacity:     busy ? 0.5 : 1,
        color:       done ? '#4ADE80' : '#6B7A99',
        borderColor: done ? 'rgba(74,222,128,0.4)' : '#252D40',
      }}
      onMouseEnter={(e) => {
        if (!busy && !done) {
          ;(e.currentTarget as HTMLElement).style.borderColor = '#6B7A99'
          ;(e.currentTarget as HTMLElement).style.color       = '#E8ECF0'
        }
      }}
      onMouseLeave={(e) => {
        if (!done) {
          ;(e.currentTarget as HTMLElement).style.borderColor = '#252D40'
          ;(e.currentTarget as HTMLElement).style.color       = '#6B7A99'
        }
      }}
    >
      {busy ? 'Queuing…' : done ? 'queued ✓' : 'Re-score now'}
    </button>
  )
}
