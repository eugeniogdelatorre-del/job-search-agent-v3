// /settings — MTD spend chart, per-source health, account info.
// All server-side reads use the authed SSR client (RLS sees the user).

import { createClient } from '@/lib/supabase/server'
import { SpendChart } from '@/components/SpendChart'
import { SourceHealthTable } from '@/components/SourceHealthTable'

export const dynamic = 'force-dynamic'

export default async function SettingsPage() {
  const supabase = createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  const now = new Date()
  const monthStart = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)
  )

  const [spendRes, healthRes] = await Promise.all([
    supabase
      .from('spend_tracking')
      .select('run_at, operation, model, cost_usd')
      .gte('run_at', monthStart.toISOString())
      .order('run_at', { ascending: true }),
    // 14 days of source health is enough to surface the latest per source
    // plus recent failure context.
    supabase
      .from('sources_health')
      .select('source, run_at, jobs_found, success, error_message, duration_ms')
      .gte(
        'run_at',
        new Date(Date.now() - 14 * 24 * 3600 * 1000).toISOString()
      )
      .order('run_at', { ascending: false })
      .limit(1000),
  ])

  const spendRows = spendRes.data ?? []
  const mtdUsd = spendRows.reduce(
    (acc, r) => acc + Number(r.cost_usd ?? 0),
    0
  )

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Signed in as {user?.email ?? 'unknown'}
        </p>
      </div>

      {spendRes.error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Spend load failed: {spendRes.error.message}
        </div>
      ) : (
        <SpendChart rows={spendRows} capUsd={8} mtdUsd={mtdUsd} />
      )}

      {healthRes.error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          Source health load failed: {healthRes.error.message}
        </div>
      ) : (
        <SourceHealthTable rows={healthRes.data ?? []} />
      )}

      <div className="rounded-lg border bg-card p-4 text-sm">
        <h2 className="text-base font-semibold">Account</h2>
        <p className="mt-1 text-muted-foreground">
          Single-user install. Magic-link only. Rotate API keys by setting the
          relevant secret in GitHub (Actions) and Vercel (Project → Environment
          Variables). Data retention is 60 days on jobs — applications carry
          snapshot fields so the tracker survives deletion.
        </p>
      </div>
    </main>
  )
}
