// /week — top 100 by match% over the last 7 days. NavBar is in layout.tsx.

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { FilterBar } from '@/components/FilterBar'
import { JobList, JobListSkeleton } from '@/components/JobList'
import { ExportMenu } from '@/components/ExportMenu'
import { parseFilters, filtersToSearchParams } from '@/lib/filters'

export const dynamic = 'force-dynamic'

export default async function WeekPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const filters = parseFilters(searchParams)

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1
            className="font-heading font-extrabold"
            style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
          >
            Week
          </h1>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            Top 100 jobs from the last 7 days, ranked by AI match score
          </p>
        </div>
        <ExportMenu
          scopeSinceDays={7}
          currentSearch={filtersToSearchParams(filters).toString()}
        />
      </div>
      <FilterBar hidePostedWithin />
      <Suspense fallback={<JobListSkeleton />}>
        <JobList filters={filters} scopeSinceDays={7} limit={100} />
      </Suspense>
    </main>
  )
}
