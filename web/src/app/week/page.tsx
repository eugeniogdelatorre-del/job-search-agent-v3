// /week — top 100 by match% over the last 7 days.

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { NavBar } from '@/components/NavBar'
import { FilterBar } from '@/components/FilterBar'
import { JobList } from '@/components/JobList'
import { ExportMenu } from '@/components/ExportMenu'
import { parseFilters, filtersToSearchParams } from '@/lib/filters'

export const dynamic = 'force-dynamic'

export default async function WeekPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const filters = parseFilters(searchParams)

  return (
    <>
      <NavBar email={user.email} />
      <main className="mx-auto max-w-7xl space-y-4 p-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">This week</h1>
            <p className="text-sm text-muted-foreground">
              Top 100 jobs from the last 7 days, ranked by AI match score.
            </p>
          </div>
          <ExportMenu
            scopeSinceDays={7}
            currentSearch={filtersToSearchParams(filters).toString()}
          />
        </div>
        <FilterBar hidePostedWithin />
        <Suspense fallback={null}>
          <JobList filters={filters} scopeSinceDays={7} limit={100} />
        </Suspense>
      </main>
    </>
  )
}
