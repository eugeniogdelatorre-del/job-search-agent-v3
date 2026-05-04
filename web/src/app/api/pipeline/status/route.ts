// GET /api/pipeline/status?runId=<number>
// Polls GitHub Actions for the current state of a pipeline.yml run.
// Returns a normalized stage + per-job statuses for the dashboard button.

import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const GH_API = 'https://api.github.com'

type JobStatus = 'queued' | 'in_progress' | 'completed'
type Stage = 'scrape' | 'classify' | 'cv-score' | 'done' | 'failed'
type Conclusion = 'success' | 'failure' | null

interface StatusResponse {
  stage: Stage
  conclusion: Conclusion
  jobs: {
    scrape: JobStatus
    classify: JobStatus
    'cv-score': JobStatus
  }
}

function ghHeaders(pat: string) {
  return {
    Authorization: `Bearer ${pat}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  }
}

function toJobStatus(s: string | null | undefined): JobStatus {
  if (s === 'in_progress') return 'in_progress'
  if (s === 'completed') return 'completed'
  return 'queued'
}

function deriveStage(
  jobs: StatusResponse['jobs'],
  conclusions: Record<string, string | null>
): { stage: Stage; conclusion: Conclusion } {
  // Any job failed → pipeline failed.
  if (Object.values(conclusions).some((c) => c === 'failure' || c === 'cancelled')) {
    return { stage: 'failed', conclusion: 'failure' }
  }

  // All completed with success → done.
  if (
    jobs.scrape === 'completed' &&
    jobs.classify === 'completed' &&
    jobs['cv-score'] === 'completed'
  ) {
    return { stage: 'done', conclusion: 'success' }
  }

  // Derive active stage.
  if (jobs['cv-score'] === 'in_progress') return { stage: 'cv-score', conclusion: null }
  if (jobs.classify === 'in_progress' || jobs.classify === 'completed') {
    return { stage: 'classify', conclusion: null }
  }
  return { stage: 'scrape', conclusion: null }
}

export async function GET(req: NextRequest) {
  // Auth gate to match the rest of /api. Status data isn't catastrophic
  // to leak, but unauthenticated polling could be used to fingerprint our
  // cron schedule and there's no reason to allow it.
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

  const runId = req.nextUrl.searchParams.get('runId')
  if (!runId) {
    return NextResponse.json({ error: 'runId required' }, { status: 400 })
  }

  const res = await fetch(
    `${GH_API}/repos/${owner}/${repo}/actions/runs/${runId}/jobs`,
    { headers: ghHeaders(pat) }
  )

  if (!res.ok) {
    return NextResponse.json(
      { error: 'GitHub API error', status: res.status },
      { status: 502 }
    )
  }

  const data = (await res.json()) as {
    jobs: Array<{ name: string; status: string; conclusion: string | null }>
  }

  const byName: Record<string, { status: string; conclusion: string | null }> = {}
  for (const job of data.jobs ?? []) {
    byName[job.name] = { status: job.status, conclusion: job.conclusion }
  }

  const jobStatuses: StatusResponse['jobs'] = {
    scrape: toJobStatus(byName['scrape']?.status),
    classify: toJobStatus(byName['classify']?.status),
    'cv-score': toJobStatus(byName['cv-score']?.status),
  }

  const conclusions: Record<string, string | null> = {
    scrape: byName['scrape']?.conclusion ?? null,
    classify: byName['classify']?.conclusion ?? null,
    'cv-score': byName['cv-score']?.conclusion ?? null,
  }

  const { stage, conclusion } = deriveStage(jobStatuses, conclusions)

  const body: StatusResponse = {
    stage,
    conclusion,
    jobs: jobStatuses,
  }

  return NextResponse.json(body)
}
