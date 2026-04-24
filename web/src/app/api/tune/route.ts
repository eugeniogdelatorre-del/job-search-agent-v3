// POST /api/tune — replace scoring_config.config (single-row table, id=1).
// We intentionally accept any JSON object: the Python scorer deep-merges
// this over DEFAULT_CONFIG in score.py, so partial overrides are fine.
// Validation here is shape-only (must be an object), not field-level —
// the scorer tolerates unknown keys.

import { NextRequest, NextResponse } from 'next/server'
import { createClient as createServerClient } from '@/lib/supabase/server'
import { createClient } from '@supabase/supabase-js'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const supabase = createServerClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let body: unknown
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }
  if (
    !body ||
    typeof body !== 'object' ||
    Array.isArray(body) ||
    !('config' in body)
  ) {
    return NextResponse.json(
      { error: 'body must be { config: object }' },
      { status: 400 }
    )
  }
  const config = (body as { config: unknown }).config
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    return NextResponse.json(
      { error: 'config must be an object' },
      { status: 400 }
    )
  }

  // scoring_config is a public-readable single row. Updates need the
  // service role because we haven't written a user-scoped write policy
  // (by design — only the logged-in owner hits this route anyway).
  const serviceUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const serviceKey = process.env.SUPABASE_SERVICE_KEY
  if (!serviceUrl || !serviceKey) {
    return NextResponse.json(
      { error: 'service role not configured on server' },
      { status: 500 }
    )
  }
  const admin = createClient(serviceUrl, serviceKey, {
    auth: { persistSession: false },
  })

  const { error } = await admin
    .from('scoring_config')
    .update({ config, updated_at: new Date().toISOString() })
    .eq('id', 1)

  if (error) {
    return NextResponse.json(
      { error: `update failed: ${error.message}` },
      { status: 500 }
    )
  }

  return NextResponse.json({ ok: true })
}
