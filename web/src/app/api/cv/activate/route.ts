// POST /api/cv/activate
// Body: { resume_id: uuid }
//
// Atomically flips ``is_active`` set-wise via the ``set_active_resume``
// Postgres function. The previous implementation did two separate
// UPDATEs (deactivate-all-others, then activate-target) with a window
// in between where the user had zero active CVs — cv_score running in
// that window could score nothing or score against null (audit H12).
//
// Requires the SQL in ``web/sql/001_resumes_set_active.sql`` to have
// been applied. If the RPC isn't present, the route returns 500 with a
// clear "function not found" error pointing at the migration.

import { NextRequest, NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let body: { resume_id?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid JSON' }, { status: 400 })
  }
  const resumeId = body.resume_id
  if (!resumeId || typeof resumeId !== 'string') {
    return NextResponse.json({ error: 'resume_id required' }, { status: 400 })
  }

  const { error } = await supabase.rpc('set_active_resume', {
    p_user_id: user.id,
    p_resume_id: resumeId,
  })
  if (error) {
    // Distinguish "not found / not owned" from other failures so the
    // client can show a sensible message (the RPC raises with that
    // exact text — see the migration SQL).
    if (/resume not found/i.test(error.message)) {
      return NextResponse.json({ error: 'not found' }, { status: 404 })
    }
    // Audit N-M1: generic error to client; log server-side.
    console.error('[api/cv/activate] rpc failed:', error.message, error.code)
    return NextResponse.json({ error: 'activate failed' }, { status: 500 })
  }

  return NextResponse.json({ resume_id: resumeId, is_active: true })
}
