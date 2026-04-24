// /archive — last 60 days, full filters, paginated table (50/page).

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { NavBar } from '@/components/NavBar'
import { FilterBar } from '@/components/FilterBar'
import { ArchiveTable } from '@/components/ArchiveTable'
import { parseFilters } from '@/lib/filters'

export const dynamic = 'force-dynamic'

export default async function ArchivePage({
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
  const pageRaw = Array.isArray(searchParams.page)
    ? searchParams.page[0]
    : searchParams.page
  const page = Math.max(1, Number(pageRaw) || 1)

  return (
    <>
      <NavBar email={user.email} />
      <main className="mx-auto max-w-7xl space-y-4 p-4">
        <div>
          <h1 className="text-xl font-semibold">Archive</h1>
          <p className="text-sm text-muted-foreground">
            Last 60 days. Jobs cycle out after 60d per retention policy.
          </p>
        </div>
        <FilterBar />
        <Suspense fallback={null}>
          <ArchiveTable filters={filters} page={page} />
        </Suspense>
      </main>
    </>
  )
}
