// GET /api/spend — month-to-date spend summary.
// Used by /settings's SpendChart. Also usable as a read-only API.

import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function GET() {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  // First of the current month (UTC). Supabase stores run_at as timestamptz
  // — comparing against an ISO string in UTC is correct.
  const now = new Date()
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))

  const { data, error } = await supabase
    .from('spend_tracking')
    .select('run_at, operation, model, cost_usd, input_tokens, cached_input_tokens, output_tokens')
    .gte('run_at', monthStart.toISOString())
    .order('run_at', { ascending: true })

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }
  const rows = data ?? []
  const mtd_usd = rows.reduce((acc, r) => acc + Number(r.cost_usd ?? 0), 0)

  return NextResponse.json({
    month_start: monthStart.toISOString(),
    mtd_usd,
    cap_usd: 8,
    rows,
  })
}
