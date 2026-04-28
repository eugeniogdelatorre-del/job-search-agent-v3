'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { ScoreBreakdownPanel } from '@/components/ScoreBreakdownPanel'
import type { JobWithScore } from '@/types/db'

type Props = {
  rows: JobWithScore[]
  savedApplications: Record<string, string>
}

export function JobGrid({ rows, savedApplications }: Props) {
  const [focusedJob, setFocusedJob] = useState<JobWithScore | null>(null)

  if (focusedJob === null) {
    return (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((job) => (
          <JobCard
            key={job.id}
            job={job}
            savedApplicationId={savedApplications[job.id] ?? null}
            onFocus={setFocusedJob}
          />
        ))}
      </div>
    )
  }

  const score = focusedJob.job_scores?.[0]

  return (
    <div className="flex flex-col items-center">
      {/* Back bar */}
      <div className="w-full max-w-2xl mb-3 flex items-center justify-between">
        <button
          onClick={() => setFocusedJob(null)}
          className="flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 font-mono text-[11px] transition-colors"
          style={{
            background: 'rgba(107,122,153,0.08)',
            border: '1px solid #252D40',
            color: '#A0AABB',
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLElement).style.borderColor = '#6B7A99'
            ;(e.currentTarget as HTMLElement).style.color = '#E8ECF0'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLElement).style.borderColor = '#252D40'
            ;(e.currentTarget as HTMLElement).style.color = '#A0AABB'
          }}
        >
          ← back to {rows.length} jobs
        </button>
        <button
          onClick={() => setFocusedJob(null)}
          className="flex items-center justify-center w-7 h-7 rounded-[6px] font-mono text-[13px] transition-colors"
          style={{ background: 'rgba(107,122,153,0.08)', border: '1px solid #252D40', color: '#A0AABB' }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLElement).style.borderColor = '#6B7A99'
            ;(e.currentTarget as HTMLElement).style.color = '#E8ECF0'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLElement).style.borderColor = '#252D40'
            ;(e.currentTarget as HTMLElement).style.color = '#A0AABB'
          }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Focused card + breakdown */}
      <div
        className="w-full max-w-2xl rounded-[12px] overflow-hidden"
        style={{ border: '1px solid rgba(0,212,255,0.2)', background: '#0A0C10' }}
      >
        {/* Cyan accent line at top */}
        <div
          className="h-px w-full"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(0,212,255,0.5), transparent)' }}
        />

        <div className="p-4">
          <JobCard
            job={focusedJob}
            savedApplicationId={savedApplications[focusedJob.id] ?? null}
          />
        </div>

        {/* Breakdown or pending state */}
        <div className="px-4 pb-4">
          {score ? (
            <ScoreBreakdownPanel score={score} />
          ) : (
            <div
              className="flex flex-col items-center gap-2 rounded-[8px] py-5"
              style={{ background: '#0F1117', border: '1px solid #1E2330' }}
            >
              <p className="font-mono text-[12px]" style={{ color: '#A0AABB' }}>
                No AI score yet for this job
              </p>
              <p className="font-mono text-[10px]" style={{ color: '#6B7A99' }}>
                Go to the <span style={{ color: '#00D4FF' }}>Resume page</span> → click{' '}
                <span style={{ color: '#00D4FF' }}>Re-score now</span> to run AI scoring
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
