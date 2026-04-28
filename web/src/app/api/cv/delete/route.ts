import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function DELETE(req: NextRequest) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let body: { resume_id?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'invalid JSON' }, { status: 400 })
  }

  const resumeId = body.resume_id
  if (!resumeId) return NextResponse.json({ error: 'resume_id required' }, { status: 400 })

  const { data: target } = await supabase
    .from('resumes')
    .select('id, is_active')
    .eq('id', resumeId)
    .eq('user_id', user.id)
    .maybeSingle()

  if (!target) return NextResponse.json({ error: 'not found' }, { status: 404 })

  if (target.is_active) {
    return NextResponse.json(
      { error: 'Cannot delete the active CV — activate another one first' },
      { status: 400 }
    )
  }

  const { error } = await supabase
    .from('resumes')
    .delete()
    .eq('id', resumeId)
    .eq('user_id', user.id)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  return NextResponse.json({ deleted: true })
}
