// /settings — MTD spend chart, per-source health, account info. NavBar in layout.tsx.

import { createClient } from '@/lib/supabase/server'
import { SpendChart } from '@/components/SpendChart'
import { SourceHealthTable } from '@/components/SourceHealthTable'

export const dynamic = 'force-dynamic'

export default async function SettingsPage() {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  const now        = new Date()
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))

  const [spendRes, healthRes] = await Promise.all([
    supabase
      .from('spend_tracking')
      .select('run_at, operation, model, cost_usd, input_tokens, cached_input_tokens, output_tokens')
      .gte('run_at', monthStart.toISOString())
      .order('run_at', { ascending: true }),
    supabase
      .from('sources_health')
      .select('source, run_at, jobs_found, success, error_message, duration_ms')
      .gte('run_at', new Date(Date.now() - 14 * 24 * 3600 * 1000).toISOString())
      .order('run_at', { ascending: false })
      .limit(1000),
  ])

  const spendRows = spendRes.data ?? []
  const mtdUsd    = spendRows.reduce((acc, r) => acc + Number(r.cost_usd ?? 0), 0)

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <div>
        <h1
          className="font-heading font-extrabold"
          style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
        >
          Settings
        </h1>
        <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
          Signed in as {user?.email ?? 'unknown'}
        </p>
      </div>

      {spendRes.error ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Spend load failed: {spendRes.error.message}
        </div>
      ) : (
        <SpendChart rows={spendRows} capUsd={8} mtdUsd={mtdUsd} />
      )}

      {healthRes.error ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Source health load failed: {healthRes.error.message}
        </div>
      ) : (
        <SourceHealthTable rows={healthRes.data ?? []} />
      )}
    </main>
  )
}
