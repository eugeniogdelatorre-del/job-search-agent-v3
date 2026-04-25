'use client'

// JSON scorer-config editor — macOS traffic-light dots header + dark textarea.
// Validates JSON + shape before POSTing. Merges over DEFAULT_CONFIG server-side.

import { useState } from 'react'
import { toast } from 'sonner'

export function ScoringConfigEditor({ initial }: { initial: unknown }) {
  const [text,  setText]  = useState(() => JSON.stringify(initial ?? {}, null, 2))
  const [saving, setSaving] = useState(false)
  const [saved,  setSaved]  = useState(false)
  const [dirty,  setDirty]  = useState(false)

  async function save() {
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch (e) {
      toast.error(`Invalid JSON: ${e instanceof Error ? e.message : 'parse error'}`)
      return
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      toast.error('Config must be a JSON object')
      return
    }
    setSaving(true)
    try {
      const res = await fetch('/api/tune', {
        method:  'POST',
        headers: { 'content-type': 'application/json' },
        body:    JSON.stringify({ config: parsed }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string }
        throw new Error(body.error ?? 'save failed')
      }
      setSaved(true)
      setDirty(false)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  function reset() {
    setText(JSON.stringify(initial ?? {}, null, 2))
    setDirty(false)
    setSaved(false)
  }

  return (
    <div
      className="rounded-[10px] overflow-hidden"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      {/* macOS traffic-light header */}
      <div
        className="flex items-center gap-2 px-4 py-3"
        style={{ borderBottom: '1px solid #1E2330' }}
      >
        <div className="w-2 h-2 rounded-full" style={{ background: '#F87171' }} />
        <div className="w-2 h-2 rounded-full" style={{ background: '#F5A623' }} />
        <div className="w-2 h-2 rounded-full" style={{ background: '#4ADE80' }} />
        <span className="ml-2 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
          agent.config.json
        </span>
      </div>

      {/* Textarea */}
      <textarea
        value={text}
        onChange={(e) => { setText(e.target.value); setDirty(true); setSaved(false) }}
        rows={28}
        spellCheck={false}
        className="w-full focus-visible:outline-none resize-y"
        style={{
          background:  'transparent',
          color:       '#67E8F9',
          fontFamily:  'var(--font-mono)',
          fontSize:    12,
          lineHeight:  1.7,
          padding:     '16px',
          minHeight:   '200px',
        }}
      />

      {/* Footer */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderTop: '1px solid #1E2330' }}
      >
        <p className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
          Overrides merge on top of{' '}
          <code style={{ color: '#6B7A99' }}>DEFAULT_CONFIG</code>{' '}
          in{' '}
          <code style={{ color: '#6B7A99' }}>scraper/score.py</code>
        </p>
        <div className="flex gap-2">
          <button
            onClick={reset}
            disabled={!dirty || saving}
            className="font-mono text-[11px] font-medium rounded-[6px] px-3 py-1.5 transition-colors"
            style={{
              background:  'transparent',
              border:      '1px solid #252D40',
              color:       dirty ? '#A0AABB' : '#3A4460',
              cursor:      dirty ? 'pointer' : 'default',
            }}
          >
            Reset
          </button>
          <button
            onClick={save}
            disabled={!dirty || saving}
            className="font-mono text-[12px] font-semibold rounded-[7px] px-6 py-2.5 transition-all"
            style={
              saved
                ? { background: 'rgba(0,212,255,0.15)', border: '1px solid rgba(0,212,255,0.4)', color: '#00D4FF' }
                : !dirty
                ? { background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)', color: '#3A4460', cursor: 'default' }
                : { background: '#00D4FF', border: '1px solid #00D4FF', color: '#000' }
            }
          >
            {saved ? 'saved ✓' : saving ? 'saving…' : 'save config →'}
          </button>
        </div>
      </div>
    </div>
  )
}
