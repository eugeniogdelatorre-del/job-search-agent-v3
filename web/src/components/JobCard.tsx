'use client'

// JobCard — Bloomberg-terminal dark redesign.
// Hover: cyan border glow + translateY(-1px) + top shimmer line.
// Apply button toggles to "applied ✓" state and persists via /api/applications.

import { useState } from 'react'
import { toast } from 'sonner'
import { TagPill } from '@/components/TagPill'
import { MatchBadge } from '@/components/MatchBadge'
import { SaveToTrackerButton } from '@/components/SaveToTrackerButton'
import { formatRelativeDate, formatSalary } from '@/lib/format'
import type { JobWithScore } from '@/types/db'

// Rule badge — amber ≥ 70, mid 50–69, dim < 50
function RuleBadge({ score }: { score: number }) {
  const style =
    score >= 70
      ? { color: '#F5A623', background: 'rgba(245,166,35,0.10)', borderColor: 'rgba(245,166,35,0.3)' }
      : score >= 50
      ? { color: '#A0AABB', background: 'rgba(160,170,187,0.07)', borderColor: 'rgba(160,170,187,0.2)' }
      : { color: '#3A4460', background: 'transparent', borderColor: '#1E2330' }
  return (
    <span
      className="inline-flex items-center rounded border px-[7px] py-0.5 font-mono text-[10px] font-medium"
      style={style}
    >
      rule: {score}
    </span>
  )
}

export function JobCard({
  job,
  savedApplicationId,
  onFocus,
}: {
  job: JobWithScore
  savedApplicationId?: string | null
  onFocus?: (job: JobWithScore) => void
}) {
  const [hovered,  setHovered]  = useState(false)
  const [applied,  setApplied]  = useState(false)
  const [applying, setApplying] = useState(false)

  const score      = job.job_scores?.[0]
  const salary     = formatSalary(job.salary_min_usd, job.salary_max_usd)
  const applyHref  = job.apply_url ?? job.source_url ?? undefined

  async function handleApply() {
    if (applied || applying || !applyHref) return
    // Open the link
    window.open(applyHref, '_blank', 'noopener,noreferrer')
    setApplying(true)
    try {
      await fetch('/api/applications', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          job_id:                job.id,
          job_title_snapshot:    job.title,
          company_snapshot:      job.company,
          apply_url_snapshot:    applyHref,
          source_snapshot:       job.source,
        }),
      })
      setApplied(true)
    } catch {
      toast.error('Could not save to tracker')
    } finally {
      setApplying(false)
    }
  }

  // Tags: function, vertical, seniority (skip Unspecified), remote (skip Unspecified)
  const tags = (
    [job.function_category, job.vertical,
      job.seniority !== 'Unspecified' ? job.seniority : null,
      job.remote_status !== 'Unspecified' ? job.remote_status : null,
    ] as (string | null)[]
  ).filter((t): t is string => t !== null && t !== undefined)

  return (
    <div
      className={`relative flex flex-col gap-2.5 rounded-[10px] p-4 select-none ${onFocus ? 'cursor-pointer' : 'cursor-default'}`}
      style={{
        background:  '#0F1117',
        border:      `1px solid ${hovered ? 'rgba(0,212,255,0.35)' : '#1E2330'}`,
        boxShadow:   hovered
          ? '0 0 0 1px rgba(0,212,255,0.1), 0 4px 24px rgba(0,212,255,0.06)'
          : 'none',
        transform:   hovered ? 'translateY(-1px)' : 'none',
        transition:  'border-color 0.18s, box-shadow 0.18s, transform 0.18s',
      }}
      onClick={onFocus ? () => onFocus(job) : undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Top shimmer accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px rounded-t-[10px]"
        style={{
          background: hovered
            ? 'linear-gradient(90deg, transparent, rgba(0,212,255,0.5), transparent)'
            : 'transparent',
          transition: 'background 0.18s',
        }}
      />

      {/* Row 1 — title + match badge */}
      <div className="flex items-start gap-3">
        <h3
          className="flex-1 font-heading font-bold text-sm leading-snug line-clamp-2"
          style={{ color: '#E8ECF0', letterSpacing: '-0.02em' }}
        >
          {job.title}
        </h3>
        <MatchBadge score={score?.match_score ?? null} />
      </div>

      {/* Row 2 — company · location */}
      <div className="flex items-center gap-1.5 text-xs">
        <span className="font-body font-medium" style={{ color: '#A0AABB' }}>
          {job.company ?? 'Unknown'}
        </span>
        {job.location && (
          <>
            <span style={{ color: '#252D40' }}>·</span>
            <span className="font-body" style={{ color: '#6B7A99' }}>
              {job.location}
            </span>
          </>
        )}
      </div>

      {/* Row 3 — tags + rule badge */}
      {(tags.length > 0 || job.score_total != null) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {tags.map((t) => (
            <TagPill key={t} label={t} />
          ))}
          {job.score_total != null && <RuleBadge score={job.score_total} />}
        </div>
      )}

      {/* Row 4 — salary (shown when present) */}
      {salary && (
        <p className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
          {salary}
        </p>
      )}

      {/* AI verdict snippet */}
      {score?.verdict_one_liner && (
        <p
          className="font-body text-[11px] leading-relaxed italic line-clamp-2"
          style={{ color: '#6B7A99' }}
        >
          {score.verdict_one_liner}
        </p>
      )}

      {/* Row 5 — bottom bar */}
      <div className="flex items-center justify-between gap-2 mt-auto pt-1">
        <span className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
          {formatRelativeDate(job.first_seen_at)} · via {job.source}
        </span>
        <div className="flex items-center gap-1">
          <SaveToTrackerButton
            job_id={job.id}
            job_title_snapshot={job.title}
            company_snapshot={job.company}
            apply_url_snapshot={applyHref ?? null}
            source_snapshot={job.source}
            savedApplicationId={savedApplicationId}
          />
          {applyHref && (
            <button
              onClick={handleApply}
              disabled={applying}
              className="font-mono text-[10px] font-semibold rounded-[5px] px-3 py-[5px] transition-transform duration-150 hover:scale-[1.03]"
              style={
                applied
                  ? {
                      background: 'rgba(0,212,255,0.15)',
                      border: '1px solid rgba(0,212,255,0.4)',
                      color: '#00D4FF',
                    }
                  : {
                      background: '#00D4FF',
                      border: '1px solid #00D4FF',
                      color: '#000',
                    }
              }
            >
              {applied ? 'applied ✓' : 'apply →'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
