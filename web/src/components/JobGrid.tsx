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

  return (
    <div className="flex flex-col items-center">
      {/* Back bar */}
      <div className="w-full max-w-xl mb-4 flex items-center justify-between">
        <button
          onClick={() => setFocusedJob(null)}
          className="font-mono text-[11px] flex items-center gap-1.5"
          style={{ color: '#6B7A99' }}
        >
          ← back to {rows.length} jobs
        </button>
        <button
          onClick={() => setFocusedJob(null)}
          className="font-mono text-[13px]"
          style={{ color: '#3A4460' }}
          aria-label="Close"
        >
          ✕
        </button>
      </div>

      {/* Focused card — full width within max-w-xl */}
      <div className="w-full max-w-xl">
        <JobCard
          job={focusedJob}
          savedApplicationId={savedApplications[focusedJob.id] ?? null}
        />
        {/* Breakdown panel below the card */}
        {focusedJob.job_scores?.[0] && (
          <ScoreBreakdownPanel score={focusedJob.job_scores[0]} />
        )}
      </div>
    </div>
  )
}
