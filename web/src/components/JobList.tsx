// Server component. Renders a grid of JobCards for the Today/Week views.
// Query + filter + sort logic lives in lib/jobs-query.

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
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        No jobs match these filters.
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
