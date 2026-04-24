// /tune — edit the rule-based scorer's config. Single row in
// scoring_config (id=1), jsonb. We load it server-side and hand off
// to a client editor.

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

  const config = data?.config ?? {}
  const updatedAt = data?.updated_at

  return (
    <main className="mx-auto max-w-4xl space-y-4 px-4 py-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Tune scorer</h1>
        {updatedAt && (
          <p className="text-xs text-muted-foreground">
            Last saved {new Date(updatedAt).toLocaleString()}
          </p>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        Edits take effect on the next scrape (every 4 hours). To rescore the
        current set immediately, run the{' '}
        <code className="font-mono text-xs">scrape.yml</code> workflow manually
        from GitHub Actions.
      </p>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Failed to load config: {error.message}
        </div>
      ) : (
        <ScoringConfigEditor initial={config} />
      )}
    </main>
  )
}
