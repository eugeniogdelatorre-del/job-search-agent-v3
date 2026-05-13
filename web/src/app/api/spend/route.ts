// GET /api/spend — month-to-date spend summary.
// Used by /settings's SpendChart. Also usable as a read-only API.

import { NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

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
  const { data, error } = await supabase
    .from('spend_tracking')
    .select('run_at, operation, model, cost_usd, input_tokens, cached_input_tokens, output_tokens')
    .gte('run_at', monthStart.toISOString())
    .order('run_at', { ascending: true })

  if (error) {
    // Audit M6: don't leak the PostgREST error message verbatim to
    // clients — table names, constraint names, etc. show up in
    // ``error.message``. Log server-side, return a generic 500.
    console.error('[api/spend] supabase select failed:', error.message)
    return NextResponse.json({ error: 'failed to load spend data' }, { status: 500 })
  }
  const rows = data ?? []
  const mtd_usd = rows.reduce((acc, r) => acc + Number(r.cost_usd ?? 0), 0)

  return NextResponse.json(
    {
      month_start: monthStart.toISOString(),
      mtd_usd,
      cap_usd: 8,
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
