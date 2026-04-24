// Raw JSON editor for scoring_config.config. Deliberately low-tech —
// the config shape is a deep nested dict of keyword lists + weights
// (see scraper/score.py DEFAULT_CONFIG). Forms would be a wall of
// fields we'd regret; a JSON textarea is honest and fast.
//
// We validate JSON.parse + basic shape (object, not array) before
// POSTing. The Python scorer deep-merges over DEFAULT_CONFIG so
// partial overrides are the recommended pattern.

'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

export function ScoringConfigEditor({ initial }: { initial: unknown }) {
  const [text, setText] = useState(() => JSON.stringify(initial ?? {}, null, 2))
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

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
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ config: parsed }),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string }
        throw new Error(body.error ?? 'save failed')
      }
      toast.success('Scoring config saved — takes effect on next scrape')
      setDirty(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  function reset() {
    setText(JSON.stringify(initial ?? {}, null, 2))
    setDirty(false)
  }

  return (
    <div className="space-y-3">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setDirty(true)
        }}
        rows={28}
        spellCheck={false}
        className="w-full rounded-md border border-input bg-background p-3 font-mono text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Overrides merge on top of{' '}
          <code className="font-mono">DEFAULT_CONFIG</code> in{' '}
          <code className="font-mono">scraper/score.py</code>. Empty{' '}
          <code className="font-mono">{'{}'}</code> means "use defaults."
        </p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={reset} disabled={!dirty || saving}>
            Reset
          </Button>
          <Button onClick={save} disabled={!dirty || saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
