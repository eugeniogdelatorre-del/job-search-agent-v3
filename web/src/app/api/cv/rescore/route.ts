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
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { GH_API, ghHeaders, findInflightDispatch } from '@/lib/github-actions'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const GH_OWNER    = 'eugeniogdelatorre-del'
const GH_REPO     = 'job-search-agent-v3'
const GH_WORKFLOW = 'cv_score.yml'
const GH_REF      = 'main'

export async function POST(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  // Body is optional — absence means "re-score with current active CV"
  let body: { resume_id?: string } = {}
  try {
    body = await req.json()
  } catch {
    // empty body is fine
  }

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

  // ── In-flight guard ───────────────────────────────────────────────────────
  // Check BEFORE touching the resumes table. Re-activating mid-batch would
  // race the running cv_score workflow against the active-CV flip and could
  // leave scores mapped to the wrong resume_id. We'd rather refuse the
  // request than corrupt the score audit trail.
  const inflight = await findInflightDispatch(GH_OWNER, GH_REPO, GH_WORKFLOW, pat)
  if (inflight) {
    return NextResponse.json(
      {
        error: 'cv_score already running',
        runId: inflight.id,
        url: inflight.html_url,
        status: inflight.status,
      },
      { status: 409 },
    )
  }

  // ── Step 1: activate the chosen CV (if resume_id supplied) ───────────────
  // Audit H12: single atomic RPC instead of deactivate-then-activate.
  // Requires web/sql/001_resumes_set_active.sql to have been applied.
  // 2026-05-14 (Audit C3): the RPC now derives user_id from auth.uid()
  // server-side. See web/sql/008_rpc_auth_hardening.sql.
  let activated = false
  if (body.resume_id) {
    const { error: rpcErr } = await supabase.rpc('set_active_resume', {
      p_resume_id: body.resume_id,
    })
    if (rpcErr) {
      if (/resume not found/i.test(rpcErr.message)) {
        return NextResponse.json({ error: 'resume not found' }, { status: 404 })
      }
      return NextResponse.json(
        { error: `activate failed: ${rpcErr.message}` },
        { status: 500 }
      )
    }
    activated = true
  }

  // ── Step 2: dispatch cv_score.yml via GitHub API ──────────────────────────
  const dispatchUrl =
    `${GH_API}/repos/${GH_OWNER}/${GH_REPO}` +
    `/actions/workflows/${GH_WORKFLOW}/dispatches`

  const ghRes = await fetch(dispatchUrl, {
    method: 'POST',
    headers: ghHeaders(pat),
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
