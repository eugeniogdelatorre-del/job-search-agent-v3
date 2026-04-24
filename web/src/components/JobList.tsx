// Server component. Renders a grid of JobCards for the Today/Week views.
// Query + filter + sort logic lives in lib/jobs-query.

import Link from 'next/link'
import { JobCard } from '@/components/JobCard'
import { queryJobs } from '@/lib/jobs-query'
import type { Filters } from '@/lib/filters'

type Props = {
  filters: Filters
  scopeSinceDays?: number
  limit?: number
}

export async function JobList({ filters, scopeSinceDays, limit = 100 }: Props) {
  const { rows, error } = await queryJobs({
    filters,
    scopeSinceDays,
    limit,
  })

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Failed to load jobs: {error}
      </div>
    )
  }

  if (rows.length === 0) {
    const anyFiltersActive =
      !!filters.function ||
      !!filters.vertical ||
      !!filters.seniority ||
      !!filters.remote ||
      !!filters.q ||
      !!filters.salaryFloor ||
      !!filters.scoreMin ||
      !!filters.matchMin ||
      !!filters.postedWithin
    return (
      <div className="space-y-2 rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        <p>No jobs match these filters.</p>
        {anyFiltersActive && (
          <p>
            <Link href="?" className="text-primary underline">
              Reset filters
            </Link>{' '}
            or widen the time window.
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {rows.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  )
}
