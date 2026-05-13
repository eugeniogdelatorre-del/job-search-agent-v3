// JobList — server component. Renders a 3-col grid of JobCards.
// Also fetches the user's saved applications so the bookmark button
// shows the correct initial state (amber = saved, toggle to unsave).

import Link from 'next/link'
import { JobGrid } from '@/components/JobGrid'
import { queryJobs } from '@/lib/jobs-query'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { FILTER_KEYS, type Filters } from '@/lib/filters'

type Props = {
  filters: Filters
  scopeSinceDays?: number
  limit?: number
  /**
   * When true, hide jobs that don't have an AI match_score yet for the
   * active CV. The "indexed" count on the parent page is unaffected — it
   * still shows total jobs in scope. Only the visual card grid is filtered.
   */
  requireScored?: boolean
}

export async function JobList({ filters, scopeSinceDays, limit = 100, requireScored = false }: Props) {
  const supabase = await createClient()
  const { rows, error } = await queryJobs({ filters, scopeSinceDays, limit, requireScored })

  if (error) {
    return (
      <div
        className="rounded-lg border p-4 text-sm font-mono"
        style={{ borderColor: 'rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.05)', color: '#F87171' }}
      >
        Failed to load jobs: {error}
      </div>
    )
  }

  // Build job_id → application_id map so SaveToTrackerButton shows correct state
  const savedMap = new Map<string, string>()
  const user = await getCurrentUser()  // Audit N-M3
  if (user && rows.length > 0) {
    const jobIds = rows.map((r) => r.id)
    const { data: apps } = await supabase
      .from('applications')
      .select('id, job_id')
      .eq('user_id', user.id)
      .in('job_id', jobIds)
    for (const a of apps ?? []) {
      if (a.job_id) savedMap.set(a.job_id, a.id)
    }
  }

  if (rows.length === 0) {
    // Audit L5: derive from FILTER_KEYS so adding a future filter
    // automatically participates — previously a hand-built ||-chain
    // would drift.
    const anyFiltersActive = FILTER_KEYS.some((k) => {
      const v = filters[k]
      return v !== undefined && v !== null && v !== ''
    })

    // Distinguish "filters too tight" from "nothing scored yet" — when the
    // page asks for scored-only, the user's mental model is "the AI hasn't
    // caught up" not "your filters are wrong."
    const headline = requireScored && !anyFiltersActive
      ? 'no scored jobs in this window yet'
      : 'no jobs match your filters'
    const subline = requireScored && !anyFiltersActive
      ? "the AI scoring pipeline hasn't reached today's batch — check back after the next morning run"
      : null

    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3A4460" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          <line x1="8" y1="11" x2="14" y2="11"/>
        </svg>
        <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>
          {headline}
        </p>
        {subline && (
          <p className="font-mono text-[11px] max-w-[400px] text-center" style={{ color: '#3A4460' }}>
            {subline}
          </p>
        )}
        {anyFiltersActive && (
          <p className="font-mono text-[11px]" style={{ color: '#3A4460' }}>
            <Link href="?" style={{ color: '#6B7A99', textDecoration: 'underline' }}>
              try relaxing your criteria
            </Link>
          </p>
        )}
      </div>
    )
  }

  return (
    <JobGrid
      rows={rows}
      savedApplications={Object.fromEntries(savedMap)}
    />
  )
}

// Skeleton grid — used as Suspense fallback
export function JobListSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

function SkeletonCard() {
  return (
    <div
      className="flex flex-col gap-3 rounded-[10px] p-4"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      <div className="skeleton" style={{ height: 16, width: '65%' }} />
      <div className="skeleton" style={{ height: 13, width: '45%' }} />
      <div className="flex gap-1.5">
        <div className="skeleton" style={{ height: 20, width: 72, borderRadius: 20 }} />
        <div className="skeleton" style={{ height: 20, width: 56, borderRadius: 20 }} />
        <div className="skeleton" style={{ height: 20, width: 64, borderRadius: 20 }} />
      </div>
      <div className="flex items-center justify-between mt-1">
        <div className="skeleton" style={{ height: 11, width: '30%' }} />
        <div className="skeleton" style={{ height: 26, width: 68, borderRadius: 5 }} />
      </div>
    </div>
  )
}
