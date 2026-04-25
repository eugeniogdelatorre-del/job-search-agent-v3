// POST /api/cv/rescore
// Body (optional): { resume_id?: string }
//
// Two steps:
//   1. If resume_id is provided → activate that CV (same logic as
//      /api/cv/activate; deactivate others first to respect the unique
//      partial index, then flip the target active).
//   2. Dispatch the cv_score.yml workflow via GitHub workflow_dispatch.
//      Requires GITHUB_PAT env var with actions:write (workflow) scope.
//
// Returns 204-equivalent JSON on success:
//   { activated: boolean, dispatched: true, message: string }
//
// Setup: create a fine-grained PAT at
//   https://github.com/settings/personal-access-tokens/new
//   → Repository access: only job-search-agent-v3
//   → Permissions → Actions: Read & Write
// Then add GITHUB_PAT to Vercel env (Production scope).

import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const GH_OWNER    = 'eugeniogdelatorre-del'
const GH_REPO     = 'job-search-agent-v3'
const GH_WORKFLOW = 'cv_score.yml'
const GH_REF      = 'main'

export async function POST(req: NextRequest) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  // Body is optional — absence means "re-score with current active CV"
  let body: { resume_id?: string } = {}
  try {
    body = await req.json()
  } catch {
    // empty body is fine
  }

  // ── Step 1: activate the chosen CV (if resume_id supplied) ───────────────
  let activated = false
  if (body.resume_id) {
    const resumeId = body.resume_id

    const { data: target } = await supabase
      .from('resumes')
      .select('id')
      .eq('id', resumeId)
      .eq('user_id', user.id)
      .maybeSingle()

    if (!target) {
      return NextResponse.json({ error: 'resume not found' }, { status: 404 })
    }

    // Deactivate all others first (avoids partial-index violation)
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
    activated = true
  }

  // ── Step 2: dispatch cv_score.yml via GitHub API ──────────────────────────
  const pat = process.env.GITHUB_PAT
  if (!pat) {
    return NextResponse.json(
      {
        error:
          'GITHUB_PAT not configured. ' +
          'Create a fine-grained PAT with Actions:write on this repo, ' +
          'then add GITHUB_PAT to Vercel → Settings → Environment Variables (Production).',
      },
      { status: 503 }
    )
  }

  const dispatchUrl =
    `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}` +
    `/actions/workflows/${GH_WORKFLOW}/dispatches`

  const ghRes = await fetch(dispatchUrl, {
    method: 'POST',
    headers: {
      Accept:                'application/vnd.github+json',
      Authorization:         `Bearer ${pat}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type':        'application/json',
      'User-Agent':          'job-search-agent-v3',
    },
    body: JSON.stringify({ ref: GH_REF }),
  })

  // GitHub returns 204 No Content on success
  if (!ghRes.ok) {
    const text = await ghRes.text().catch(() => '')
    return NextResponse.json(
      { error: `GitHub dispatch failed (${ghRes.status}): ${text}` },
      { status: 502 }
    )
  }

  return NextResponse.json({
    activated,
    dispatched: true,
    message: activated
      ? 'CV activated and re-score queued — scores update in a few minutes'
      : 'Re-score queued — scores update in a few minutes',
  })
}
