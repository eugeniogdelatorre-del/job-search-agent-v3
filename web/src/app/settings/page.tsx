// /settings — MTD spend chart, per-source health, account info. NavBar in layout.tsx.

import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { SpendChart } from '@/components/SpendChart'
import { SourceHealthTable } from '@/components/SourceHealthTable'
import { MONTHLY_CAP_USD } from '@/lib/budget-config'

export const dynamic = 'force-dynamic'

// 2026-05-14 (Audit H7): same pagination ceiling used for the spend
// fetch as for the active-jobs fetch. Spend volume is far lower (~1
// row per batch, dozens per month) so this only kicks in after a
// remediation run that logs a lot of per-job rows.
const SPEND_PAGE = 1000
const SPEND_MAX_PAGES = 50

export default async function SettingsPage() {
  const supabase = await createClient()
  const user = await getCurrentUser()  // Audit N-M3

  const now         = new Date()
  const monthStart  = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
  const todayStart  = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))

  // sources_health doesn't need pagination — capped at 1000 by the
  // .limit() below and we genuinely don't care about runs older than
  // the most recent ~1000 across 14 days.
  const healthRes = await supabase
    .from('sources_health')
    .select('source, run_at, jobs_found, success, error_message, duration_ms')
    .gte('run_at', new Date(Date.now() - 14 * 24 * 3600 * 1000).toISOString())
    .order('run_at', { ascending: false })
    .limit(1000)

  // Paginated spend fetch — see comment at SPEND_PAGE definition.
  // Row type is inferred from Supabase's PostgREST response (which uses
  // nullable columns). The SpendChart prop type expects non-null fields;
  // we filter to those shape-conformant rows before rendering.
  const spendRowsRaw: Array<{
    run_at: string
    operation: string | null
    model: string | null
    cost_usd: number | null
    input_tokens: number | null
    cache_write_input_tokens: number | null
    cached_input_tokens: number | null
    output_tokens: number | null
  }> = []
  let spendErr: { message: string } | null = null
  for (let i = 0; i < SPEND_MAX_PAGES; i += 1) {
    const from = i * SPEND_PAGE
    const to   = from + SPEND_PAGE - 1
    const res  = await supabase
      .from('spend_tracking')
      .select('run_at, operation, model, cost_usd, input_tokens, cache_write_input_tokens, cached_input_tokens, output_tokens')
      .gte('run_at', monthStart.toISOString())
      .order('run_at', { ascending: true })
      .range(from, to)
    if (res.error) { spendErr = res.error; break }
    const batch = res.data ?? []
    spendRowsRaw.push(...batch)
    if (batch.length < SPEND_PAGE) break
  }
  // Coerce to the SpendChart row shape: drop rows missing operation
  // (we can't classify them in the stacked bar without one) and treat
  // null cost as 0. Same semantics the SpendChart code used implicitly
  // before, made explicit here.
  const spendRows = spendRowsRaw
    .filter((r): r is typeof r & { operation: string } => r.operation !== null)
    .map((r) => ({
      run_at: r.run_at,
      operation: r.operation,
      cost_usd: Number(r.cost_usd ?? 0),
      input_tokens: r.input_tokens,
      cache_write_input_tokens: r.cache_write_input_tokens,
      cached_input_tokens: r.cached_input_tokens,
      output_tokens: r.output_tokens,
    }))

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
    if (res.error) {
      // Scrub: log the PostgREST detail server-side, surface a generic flag.
      console.error('[settings] jobs load failed:', res.error.message, res.error.code)
      jobsErr = 'load failed'
      break
    }
    const batch = res.data ?? []
    allActiveJobs.push(...batch)
    if (batch.length < PAGE) break  // last page
  }
  if (spendErr) console.error('[settings] spend load failed:', spendErr.message)
  if (healthRes.error) console.error('[settings] source health load failed:', healthRes.error.message, healthRes.error.code)

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

  const mtdUsd = spendRows.reduce((acc, r) => acc + r.cost_usd, 0)

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

      {spendErr ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Spend load failed — try again
        </div>
      ) : (
        <SpendChart rows={spendRows} capUsd={MONTHLY_CAP_USD} mtdUsd={mtdUsd} />
      )}

      {healthRes.error || jobsErr ? (
        <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
          Source health load failed — try again
        </div>
      ) : (
        <SourceHealthTable rows={healthRes.data ?? []} perSource={perSource} />
      )}
    </main>
  )
}
