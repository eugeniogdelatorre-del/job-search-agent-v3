// GET /api/spend — month-to-date spend summary.
// Used by /settings's SpendChart. Also usable as a read-only API.

import { NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { MONTHLY_CAP_USD } from '@/lib/budget-config'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

// 2026-05-14 (Audit H7): paginate the spend_tracking fetch instead of
// trusting a single .select() to return everything. PostgREST silently
// caps each request at 1000 rows (server-side `db.max_rows`). At our
// current ~1 row/batch volume we're fine, but after any remediation run
// (rescore, dedup repair) that logs 100+ rows in a day, an unpaginated
// fetch would under-count `mtd_usd` and miscolour the chart. Hard
// ceiling at 50 pages = 50k rows = many months of normal operation.
const PAGE = 1000
const MAX_PAGES = 50

export async function GET() {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  // First of the current month (UTC). Supabase stores run_at as timestamptz
  // — comparing against an ISO string in UTC is correct.
  const now = new Date()
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))

  // Audit M5: `spend_tracking` is currently a global table (no user_id
  // column — every pipeline run shares one). Since this is single-tenant
  // today the response is fine, but mark the cache as `private` so a
  // shared cache (Vercel CDN, browser back-cache) can't leak it to a
  // future second user. Document the intent.
  type SpendRow = {
    run_at: string
    operation: string | null
    model: string | null
    cost_usd: number | null
    input_tokens: number | null
    cached_input_tokens: number | null
    output_tokens: number | null
  }
  const rows: SpendRow[] = []
  for (let i = 0; i < MAX_PAGES; i += 1) {
    const from = i * PAGE
    const to   = from + PAGE - 1
    const { data, error } = await supabase
      .from('spend_tracking')
      .select('run_at, operation, model, cost_usd, input_tokens, cached_input_tokens, output_tokens')
      .gte('run_at', monthStart.toISOString())
      .order('run_at', { ascending: true })
      .range(from, to)
    if (error) {
      // Audit M6: don't leak the PostgREST error message verbatim to
      // clients — table names, constraint names, etc. show up in
      // ``error.message``. Log server-side, return a generic 500.
      console.error('[api/spend] supabase select failed:', error.message)
      return NextResponse.json({ error: 'failed to load spend data' }, { status: 500 })
    }
    const batch = (data ?? []) as SpendRow[]
    rows.push(...batch)
    if (batch.length < PAGE) break  // last page
  }
  // M3-new (2026-05-20): fail loud if pagination cap was hit. Silently
  // breaking would under-count MTD, making the UI show headroom that the
  // Python kill-switch doesn't see. Mirror scraper/budget.py's fail-closed
  // philosophy: a wrong total is worse than an error the operator notices.
  if (rows.length >= MAX_PAGES * PAGE) {
    console.error('[api/spend] paged past MAX_PAGES safety cap — MTD total is under-counted')
    return NextResponse.json(
      { error: 'spend data exceeds dashboard cap; check scraper logs' },
      { status: 500 },
    )
  }
  const mtd_usd = rows.reduce((acc, r) => acc + Number(r.cost_usd ?? 0), 0)

  return NextResponse.json(
    {
      month_start: monthStart.toISOString(),
      mtd_usd,
      cap_usd: MONTHLY_CAP_USD,
      rows,
    },
    {
      headers: {
        // Currently global data — but `private` prevents shared caches
        // from serving it to another user if the table ever gets a
        // user_id dimension.
        'cache-control': 'private, max-age=10',
      },
    },
  )
}
