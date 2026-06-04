// / — "Today" view. Last 24h, sorted by match% desc.
// NavBar is in layout.tsx — not repeated here.
// StatsBar pulls live counts from two parallel Supabase queries.

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { FilterBar } from '@/components/FilterBar'
import { JobList, JobListSkeleton } from '@/components/JobList'
import { StatsBar } from '@/components/StatsBar'
import { ExportMenu } from '@/components/ExportMenu'
import { RunPipelineButton } from '@/components/RunPipelineButton'
import { parseFilters, filtersToSearchParams } from '@/lib/filters'
import { queryJobs } from '@/lib/jobs-query'

export const dynamic = 'force-dynamic'

export default async function TodayPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const supabase = await createClient()
  const user = await getCurrentUser()  // Audit N-M3: cached per request
  if (!user) redirect('/login')

  const filters = parseFilters(searchParams)

  // Stats bar queries (parallel):
  //  - indexedResult: every indexed job in scope (no requireScored) → the
  //    "indexed" total shouldn't shrink when the AI is behind.
  //  - scoredResult:  requireScored over the FULL scope (withCount) so the
  //    "scored" count and "avg match" reflect every scored job, not just the
  //    60 cards rendered below. (Audit 2026-06-04 #11: previously derived from
  //    the limit:60 grid sample, which under-counted past 60 jobs/day.)
  //  - appCountResult: saved-applications count for the authed user.
  // The card grid (JobList) is decoupled and fetches its own 60-row page.
  const STAT_SCORED_CAP = 1000  // PostgREST page ceiling; avg samples up to this
  const [indexedResult, scoredResult, appCountResult] = await Promise.all([
    queryJobs({ filters, scopeSinceDays: 1, limit: 1, withCount: true }),
    queryJobs({ filters, scopeSinceDays: 1, limit: STAT_SCORED_CAP, withCount: true, requireScored: true }),
    supabase.from('applications').select('id', { count: 'exact', head: true }),
  ])

  const indexed     = indexedResult.total ?? indexedResult.rows.length
  const scored      = scoredResult.total ?? scoredResult.rows.length
  const matchScores = scoredResult.rows.flatMap((r) => r.job_scores ?? []).map((s) => s.match_score).filter((s): s is number => s != null)
  const avgMatch    = matchScores.length > 0 ? Math.round(matchScores.reduce((a, b) => a + b, 0) / matchScores.length) : null
  const savedCount  = appCountResult.count ?? 0

  const now     = new Date()
  const weekday = now.toLocaleDateString('en-US', { weekday: 'long' })
  const date    = now.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1
            className="font-heading font-extrabold"
            style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
          >
            Today
          </h1>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            {weekday}, {date} · {indexed} positions indexed
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RunPipelineButton />
          <ExportMenu
            scopeSinceDays={1}
            currentSearch={filtersToSearchParams(filters).toString()}
          />
        </div>
      </div>

      {/* Stats bar */}
      <StatsBar
        indexed={indexed}
        scored={scored}
        avgMatch={avgMatch}
        saved={savedCount}
      />

      {/* Filters */}
      <FilterBar hidePostedWithin />

      {/* Job grid — pre-fetched; Suspense wraps refetch on filter change.
          Audit H-4 (2026-05-13): removed `requireScored` so freshly-
          scraped jobs (no match_score yet) still show up. The SQL sort
          already puts scored rows first (match_score DESC NULLS LAST),
          so unscored cards land at the bottom of the grid — a
          "just scraped" tail rather than a blackout window. */}
      <Suspense fallback={<JobListSkeleton />}>
        <JobList filters={filters} scopeSinceDays={1} limit={60} />
      </Suspense>
    </main>
  )
}
