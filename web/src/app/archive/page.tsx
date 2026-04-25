// /archive — last 60 days, paginated table (50/page). NavBar is in layout.tsx.

import { Suspense } from 'react'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { FilterBar } from '@/components/FilterBar'
import { ArchiveTable } from '@/components/ArchiveTable'
import { ExportMenu } from '@/components/ExportMenu'
import { parseFilters, filtersToSearchParams } from '@/lib/filters'

export const dynamic = 'force-dynamic'

export default async function ArchivePage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>
}) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const filters  = parseFilters(searchParams)
  const pageRaw  = Array.isArray(searchParams.page) ? searchParams.page[0] : searchParams.page
  const page     = Math.max(1, Number(pageRaw) || 1)

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1
            className="font-heading font-extrabold"
            style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
          >
            Archive
          </h1>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            Last 60 days · jobs cycle out after 60d per retention policy
          </p>
        </div>
        <ExportMenu
          scopeSinceDays={60}
          currentSearch={filtersToSearchParams(filters).toString()}
        />
      </div>
      <FilterBar />
      <Suspense fallback={null}>
        <ArchiveTable filters={filters} page={page} />
      </Suspense>
    </main>
  )
}
