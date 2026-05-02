// POST /api/pipeline/run
// Triggers the pipeline.yml workflow via GitHub Actions API and returns the run ID.
// GITHUB_PAT must be a fine-grained PAT with Actions: write + Contents: read.

import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const GH_API = 'https://api.github.com'

function ghHeaders(pat: string) {
  return {
    Authorization: `Bearer ${pat}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
  }
}

export async function POST() {
  // Auth gate: this route triggers a paid GitHub Actions run (classify +
  // cv_score burn real money). Match every other /api route and require a
  // signed-in session. No anon access, full stop.
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
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

  // 1. Trigger the workflow.
  const dispatchRes = await fetch(
    `${GH_API}/repos/${owner}/${repo}/actions/workflows/pipeline.yml/dispatches`,
    {
      method: 'POST',
      headers: ghHeaders(pat),
      body: JSON.stringify({ ref: 'main' }),
    }
  )

  if (dispatchRes.status !== 204) {
    return NextResponse.json(
      { error: 'GitHub dispatch failed', status: dispatchRes.status },
      { status: 502 }
    )
  }

  // 2. Wait for GitHub to create the run record.
  await new Promise((r) => setTimeout(r, 3000))

  // 3. Find the newly queued run.
  const runsRes = await fetch(
    `${GH_API}/repos/${owner}/${repo}/actions/runs?per_page=5&event=workflow_dispatch`,
    { headers: ghHeaders(pat) }
  )
  const runsData = (await runsRes.json()) as {
    workflow_runs?: Array<{ id: number; name: string; created_at: string }>
  }
  const pipelineRun = (runsData.workflow_runs ?? [])
    .filter((r) => r.name === 'pipeline')
    .at(0)

  return NextResponse.json({ runId: pipelineRun?.id ?? null })
}
