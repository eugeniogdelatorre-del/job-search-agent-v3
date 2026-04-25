// JobList — server component. Renders a 3-col grid of JobCards with the
// Bloomberg-terminal dark skeleton and empty state per the design spec.

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
  const { rows, error } = await queryJobs({ filters, scopeSinceDays, limit })

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

  if (rows.length === 0) {
    const anyFiltersActive =
      !!filters.function || !!filters.vertical || !!filters.seniority ||
      !!filters.remote   || !!filters.q        || !!filters.salaryFloor ||
      !!filters.scoreMin || !!filters.matchMin  || !!filters.postedWithin

    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3A4460" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          <line x1="8" y1="11" x2="14" y2="11"/>
        </svg>
        <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>
          no jobs match your filters
        </p>
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
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {rows.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
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
      {/* Title */}
      <div className="skeleton" style={{ height: 16, width: '65%' }} />
      {/* Company */}
      <div className="skeleton" style={{ height: 13, width: '45%' }} />
      {/* Tags */}
      <div className="flex gap-1.5">
        <div className="skeleton" style={{ height: 20, width: 72, borderRadius: 20 }} />
        <div className="skeleton" style={{ height: 20, width: 56, borderRadius: 20 }} />
        <div className="skeleton" style={{ height: 20, width: 64, borderRadius: 20 }} />
      </div>
      {/* Bottom */}
      <div className="flex items-center justify-between mt-1">
        <div className="skeleton" style={{ height: 11, width: '30%' }} />
        <div className="skeleton" style={{ height: 26, width: 68, borderRadius: 5 }} />
      </div>
    </div>
  )
}
