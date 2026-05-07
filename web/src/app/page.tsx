// / — "Today" view. Last 24h, sorted by match% desc.
// NavBar is in layout.tsx — not repeated here.
// StatsBar pulls live counts from two parallel Supabase queries.

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
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
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const filters = parseFilters(searchParams)

  // Run jobs query + applications count in parallel for the stats bar.
  // We DON'T pass requireScored here so `total` reflects every indexed
  // job in scope — the "indexed" stat shouldn't shrink when the AI is
  // behind. The card grid below uses requireScored=true to hide unscored
  // rows; counts and visuals are intentionally decoupled.
  const [jobsResult, appCountResult] = await Promise.all([
    queryJobs({ filters, scopeSinceDays: 1, limit: 60, withCount: true }),
    supabase.from('applications').select('id', { count: 'exact', head: true }),
  ])

  const { rows, total } = jobsResult
  const indexed     = total ?? rows.length
  const scored      = rows.filter((r) => r.job_scores?.[0]?.match_score != null).length
  const matchScores = rows.flatMap((r) => r.job_scores ?? []).map((s) => s.match_score).filter((s): s is number => s != null)
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
          requireScored hides cards the AI hasn't reached yet. The header
          counter still displays the full indexed total above. */}
      <Suspense fallback={<JobListSkeleton />}>
        <JobList filters={filters} scopeSinceDays={1} limit={60} requireScored />
      </Suspense>
    </main>
  )
}
