// / — "Today" view. Last 24h, default sort match% desc (with null fallback
// to rule-based score_total desc in Phase 5 since nothing is AI-scored yet).

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { NavBar } from '@/components/NavBar'
import { FilterBar } from '@/components/FilterBar'
import { JobList } from '@/components/JobList'
import { ExportMenu } from '@/components/ExportMenu'
import { parseFilters, filtersToSearchParams } from '@/lib/filters'

export const dynamic = 'force-dynamic'

export default async function TodayPage({
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
            <h1 className="text-xl font-semibold">Today</h1>
            <p className="text-sm text-muted-foreground">
              Jobs seen in the last 24 hours, ranked by AI match score. Match
              % populates once a CV is activated (Phase 6).
            </p>
          </div>
          <ExportMenu
            scopeSinceDays={1}
            currentSearch={filtersToSearchParams(filters).toString()}
          />
        </div>
        <FilterBar hidePostedWithin />
        <Suspense fallback={<ListSkeleton />}>
          <JobList filters={filters} scopeSinceDays={1} limit={60} />
        </Suspense>
      </main>
    </>
  )
}

function ListSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-44 animate-pulse rounded-lg border bg-muted/40" />
      ))}
    </div>
  )
}
