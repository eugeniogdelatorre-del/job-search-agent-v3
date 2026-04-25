// /tune — JSON scorer config editor. NavBar is in layout.tsx.

import { createClient } from '@/lib/supabase/server'
import { ScoringConfigEditor } from '@/components/ScoringConfigEditor'

export const dynamic = 'force-dynamic'

export default async function TunePage() {
  const supabase = createClient()
  const { data, error } = await supabase
    .from('scoring_config')
    .select('config, updated_at')
    .eq('id', 1)
    .maybeSingle()

  const config    = data?.config ?? {}
  const updatedAt = data?.updated_at

  return (
    <main className="mx-auto max-w-4xl space-y-4 px-4 py-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1
            className="font-heading font-extrabold"
            style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
          >
            Tune
          </h1>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            Edits take effect on the next scrape (every 4 hours)
          </p>
        </div>
        {updatedAt && (
          <p className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
            Last saved {new Date(updatedAt).toLocaleString()}
          </p>
        )}
      </div>

      {error ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Failed to load config: {error.message}
        </div>
      ) : (
        <ScoringConfigEditor initial={config} />
      )}
    </main>
  )
}
