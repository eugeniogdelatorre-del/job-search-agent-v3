// GET /api/pipeline/status?runId=<number>
// Polls GitHub Actions for the current state of a pipeline.yml run.
// Returns a normalized stage + per-job statuses for the dashboard button.

import { NextRequest, NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'

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
  await createClient()  // ensure middleware-refreshed cookies are loaded
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

  const runId = req.nextUrl.searchParams.get('runId')
  // Audit H15: runId is interpolated into a GitHub API URL. An attacker
  // could supply something like `12345/../meta` and probe unrelated
  // endpoints with our PAT. Restrict to a positive integer.
  if (!runId || !/^\d+$/.test(runId)) {
    return NextResponse.json({ error: 'runId must be a positive integer' }, { status: 400 })
  }

  // Audit N-H5: confirm the run belongs to pipeline.yml. Without this,
  // an authed user could poll any workflow run in the repo and read its
  // job structure via our PAT. The /actions/runs/{id} endpoint returns
  // the workflow file path.
  const runMetaRes = await fetch(
    `${GH_API}/repos/${owner}/${repo}/actions/runs/${runId}`,
    { headers: ghHeaders(pat), cache: 'no-store' },
  )
  if (runMetaRes.status === 404) {
    return NextResponse.json({ error: 'run not found' }, { status: 404 })
  }
  if (!runMetaRes.ok) {
    console.error('[api/pipeline/status] meta fetch failed:', runMetaRes.status)
    return NextResponse.json({ error: 'GitHub API error', status: runMetaRes.status }, { status: 502 })
  }
  const runMeta = (await runMetaRes.json()) as { path?: string; created_at?: string }
  if (runMeta.path !== '.github/workflows/pipeline.yml') {
    return NextResponse.json({ error: 'run does not belong to pipeline.yml' }, { status: 403 })
  }

  // Audit M9 (2026-05-14): reject very old runIds. The status endpoint
  // is meant for polling an in-flight run dispatched ~minutes ago. An
  // attacker who knows an old runId could repeatedly hit this route to
  // exhaust the PAT's 5000-req/hr rate limit via the downstream
  // /jobs call below. 1 hour is well past pipeline.yml's ~25-min
  // wall-time so legitimate clients are never affected.
  if (runMeta.created_at) {
    const ageMs = Date.now() - Date.parse(runMeta.created_at)
    if (Number.isFinite(ageMs) && ageMs > 60 * 60 * 1000) {
      return NextResponse.json(
        { error: 'run is older than 1 hour; status polling only supports recent runs' },
        { status: 410 }
      )
    }
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

  // Audit M8: front-end polls every 10s, which burns the GitHub PAT's
  // 5000/hr rate limit fast under any kind of load. A short private
  // cache lets us coalesce bursts of polls (e.g. React strict-mode
  // double renders, tab restore) without affecting UX — the UI's
  // 10-second polling cadence remains the floor on staleness.
  return NextResponse.json(body, {
    headers: { 'cache-control': 'private, max-age=2' },
  })
}
