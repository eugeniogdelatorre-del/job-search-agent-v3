import { NextRequest, NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { findInflightDispatch } from '@/lib/github-actions'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const GH_OWNER = 'eugeniogdelatorre-del'
const GH_REPO = 'job-search-agent-v3'

export async function DELETE(req: NextRequest) {
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

  // Audit N-H9: refuse to delete while cv_score is in flight, even on a
  // non-active CV. cv_score reads `is_active` at dispatch time, so the
  // workflow may be scoring against the CV that was active when it
  // started — which could be THIS one if it was just deactivated.
  // Deleting now would orphan the job_scores rows the running workflow
  // is about to write (or break the FK if one exists).
  const pat = process.env.GITHUB_PAT
  if (pat) {
    const inflight = await findInflightDispatch(GH_OWNER, GH_REPO, 'cv_score.yml', pat)
    if (inflight) {
      return NextResponse.json(
        {
          error: 'cv_score is currently running — try again in a few minutes',
          runId: inflight.id,
          url: inflight.html_url,
        },
        { status: 409 },
      )
    }
  }

  const { error } = await supabase
    .from('resumes')
    .delete()
    .eq('id', resumeId)
    .eq('user_id', user.id)

  if (error) {
    // Audit N-M1: don't leak PostgREST internals.
    console.error('[api/cv/delete] delete failed:', error.message, error.code)
    return NextResponse.json({ error: 'delete failed' }, { status: 500 })
  }

  return NextResponse.json({ deleted: true })
}
