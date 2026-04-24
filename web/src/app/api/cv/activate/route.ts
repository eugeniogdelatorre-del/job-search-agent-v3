// POST /api/cv/activate
// Body: { resume_id: uuid }
//
// Deactivates every other resume for this user, then flips the chosen
// one active. Order matters because of the unique partial index
// `idx_resumes_one_active_per_user` — doing it the other way would
// briefly violate the constraint.
//
// RLS enforces ownership; the session client here can only touch the
// current user's rows anyway.

import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
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

  // Confirm the row exists + belongs to this user (RLS would filter it
  // out otherwise, but we want a clear 404 instead of a silent no-op).
  const { data: target, error: fetchErr } = await supabase
    .from('resumes')
    .select('id')
    .eq('id', resumeId)
    .eq('user_id', user.id)
    .maybeSingle()
  if (fetchErr) {
    return NextResponse.json({ error: fetchErr.message }, { status: 500 })
  }
  if (!target) {
    return NextResponse.json({ error: 'not found' }, { status: 404 })
  }

  const { error: deactErr } = await supabase
    .from('resumes')
    .update({ is_active: false })
    .eq('user_id', user.id)
    .neq('id', resumeId)
  if (deactErr) {
    return NextResponse.json(
      { error: `deactivate failed: ${deactErr.message}` },
      { status: 500 }
    )
  }

  const { error: actErr } = await supabase
    .from('resumes')
    .update({ is_active: true })
    .eq('id', resumeId)
    .eq('user_id', user.id)
  if (actErr) {
    return NextResponse.json(
      { error: `activate failed: ${actErr.message}` },
      { status: 500 }
    )
  }

  return NextResponse.json({ resume_id: resumeId, is_active: true })
}
