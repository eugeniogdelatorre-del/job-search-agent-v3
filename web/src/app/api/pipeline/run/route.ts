// POST /api/pipeline/run
// Triggers the pipeline.yml workflow via GitHub Actions API and returns the run ID.
// GITHUB_PAT must be a fine-grained PAT with Actions: write + Contents: read.

import { NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { GH_API, ghHeaders, findInflightDispatch } from '@/lib/github-actions'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const WORKFLOW_FILE = 'pipeline.yml'

export async function POST() {
  // Auth gate: this route triggers a paid GitHub Actions run (classify +
  // geo_filter + cv_score burn real money). Match every other /api route
  // and require a signed-in session. No anon access, full stop.
  await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  const pat = process.env.GITHUB_PAT
  const owner = process.env.GITHUB_OWNER
  const repo = process.env.GITHUB_REPO

  if (!pat || !owner || !repo) {
    return NextResponse.json(
      { error: 'GitHub integration not configured' },
      { status: 500 }
    )
  }

  // In-flight guard: refuse to dispatch if a previous run from this same
  // endpoint is still queued/in-progress. Prevents a stuck client (or a
  // double-click) from racking up duplicate Anthropic Batch spend.
  // Soft-fails to null on GitHub API hiccup so a single outage doesn't
  // lock the button forever.
  const inflight = await findInflightDispatch(owner, repo, WORKFLOW_FILE, pat)
  if (inflight) {
    return NextResponse.json(
      {
        error: 'pipeline already running',
        runId: inflight.id,
        url: inflight.html_url,
        status: inflight.status,
      },
      { status: 409 },
    )
  }

  // 1. Trigger the workflow.
  const dispatchRes = await fetch(
    `${GH_API}/repos/${owner}/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: 'POST',
      headers: ghHeaders(pat),
      body: JSON.stringify({ ref: 'main' }),
    }
  )

  if (dispatchRes.status !== 204) {
    console.error('[api/pipeline/run] dispatch returned', dispatchRes.status)
    return NextResponse.json(
      { error: 'GitHub dispatch failed', status: dispatchRes.status },
      { status: 502 }
    )
  }

  // Audit M9: previously this slept 3 seconds and then queried
  // /actions/runs?per_page=5 and name-filtered for 'pipeline'. Two
  // problems:
  //   1. 3s isn't always enough — under GitHub-side load, the run record
  //      can take longer to materialize, and the client polls null
  //      forever (H16 now handles that, but it's still wasteful).
  //   2. Filtering by ``r.name === 'pipeline'`` clashes if any other
  //      workflow happens to be named ``pipeline``.
  // Use the workflow-specific endpoint instead — narrows by file path,
  // no name-match needed. Briefly retry a few times to absorb the
  // creation latency without committing to a fixed sleep budget.
  const dispatchedAt = Date.now()
  let pipelineRun: { id: number } | undefined
  for (let attempt = 0; attempt < 5 && !pipelineRun; attempt++) {
    if (attempt > 0) await new Promise((r) => setTimeout(r, 600))
    const runsRes = await fetch(
      `${GH_API}/repos/${owner}/${repo}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=1&event=workflow_dispatch`,
      { headers: ghHeaders(pat), cache: 'no-store' },
    )
    if (!runsRes.ok) continue
    const runsData = (await runsRes.json()) as {
      workflow_runs?: Array<{ id: number; created_at: string }>
    }
    const latest = runsData.workflow_runs?.[0]
    if (!latest) continue
    // Only accept a run that was created at-or-after our dispatch (some
    // clock skew tolerance) — otherwise we might return the previous
    // run's id.
    if (new Date(latest.created_at).getTime() >= dispatchedAt - 30_000) {
      pipelineRun = latest
    }
  }

  return NextResponse.json({ runId: pipelineRun?.id ?? null })
}
