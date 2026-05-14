// /settings — MTD spend chart, per-source health, account info. NavBar in layout.tsx.

import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { SpendChart } from '@/components/SpendChart'
import { SourceHealthTable } from '@/components/SourceHealthTable'

export const dynamic = 'force-dynamic'

export default async function SettingsPage() {
  const supabase = await createClient()
  const user = await getCurrentUser()  // Audit N-M3

  const now         = new Date()
  const monthStart  = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
  const todayStart  = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

  // Two parallel queries that don't depend on pagination:
  //   - spend_tracking for the MTD chart + total
  //   - sources_health for run-level fields (status / latency / last_run / error)
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

  // 2026-05-13: PostgREST caps each request at 1000 rows (Supabase
  // server-side `db.max_rows` default), so the previous `.range(0, 10_000)`
  // was silently truncating the result. The "Live total" header showed
  // exactly 1000 instead of the real count of active jobs. Paginate the
  // fetch in 1000-row pages until we get a short page. Loop is bounded
  // by max_pages so a runaway server can't lock the request.
  const PAGE = 1000
  const MAX_PAGES = 50  // hard ceiling = 50k rows; well above our scale
  const allActiveJobs: { source: string | null; first_seen_at: string | null }[] = []
  let jobsErr: string | null = null
  for (let i = 0; i < MAX_PAGES; i += 1) {
    const from = i * PAGE
    const to   = from + PAGE - 1
    const res  = await supabase
      .from('jobs')
      .select('source, first_seen_at')
      .eq('is_active', true)
      .order('first_seen_at', { ascending: false })  // stable order across pages
      .range(from, to)
    if (res.error) { jobsErr = res.error.message; break }
    const batch = res.data ?? []
    allActiveJobs.push(...batch)
    if (batch.length < PAGE) break  // last page
  }

  // Build per-source aggregates: live total (= active rows from this
  // source) and new today (= first_seen_at on or after UTC midnight).
  const perSource: Record<string, { new_today: number; live_total: number }> = {}
  for (const j of allActiveJobs) {
    const k = j.source ?? '?'
    if (!perSource[k]) perSource[k] = { new_today: 0, live_total: 0 }
    perSource[k].live_total += 1
    if (j.first_seen_at && j.first_seen_at >= todayStart.toISOString()) {
      perSource[k].new_today += 1
    }
  }

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
        // capUsd must mirror BUDGET_CAP_USD in scraper/budget.py
        // (raised $8 → $20 on 2026-05-14).
        <SpendChart rows={spendRows} capUsd={20} mtdUsd={mtdUsd} />
      )}

      {healthRes.error || jobsErr ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Source health load failed: {healthRes.error?.message ?? jobsErr}
        </div>
      ) : (
        <SourceHealthTable rows={healthRes.data ?? []} perSource={perSource} />
      )}
    </main>
  )
}
