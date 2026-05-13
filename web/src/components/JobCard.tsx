'use client'

// JobCard — Bloomberg-terminal dark redesign.
// Hover: cyan border glow + translateY(-1px) + top shimmer line.
// Apply button opens the role in a new tab. It does NOT auto-track —
// the user explicitly bookmarks via SaveToTrackerButton when they want
// the role on the kanban.

import { useState } from 'react'
import { TagPill } from '@/components/TagPill'
import { MatchBadge } from '@/components/MatchBadge'
import { SaveToTrackerButton } from '@/components/SaveToTrackerButton'
import { ScoreBreakdownPanel } from '@/components/ScoreBreakdownPanel'
import { formatRelativeDate, formatSalary } from '@/lib/format'
import type { JobWithScore } from '@/types/db'

export function JobCard({
  job,
  savedApplicationId,
  onFocus,
}: {
  job: JobWithScore
  savedApplicationId?: string | null
  onFocus?: (job: JobWithScore) => void
}) {
  // Inline-expand toggle. Separate from the parent's `onFocus` flow (which
  // navigates to a single-card focused view) so users can scan dim bars
  // without losing grid context — useful during triage.
  const [expanded, setExpanded] = useState(false)

  const score      = job.job_scores?.[0]
  const salary     = formatSalary(job.salary_min_usd, job.salary_max_usd)
  const applyHref  = job.apply_url ?? job.source_url ?? undefined

  function handleApply() {
    if (!applyHref) return
    window.open(applyHref, '_blank', 'noopener,noreferrer')
  }

  // Tags: function, vertical, seniority, remote.
  // Audit M24: previously `job.seniority !== 'Unspecified' ? ... : null`
  // returned the value when seniority was `null` (because `null !==
  // 'Unspecified'`), so a tag pill literally labeled "null" could appear.
  // Treat BOTH the DB sentinel ('Unspecified') and SQL null as "no tag".
  // See M25 for the longer-term DB-side fix.
  const tags: string[] = (
    [
      job.function_category,
      job.vertical,
      job.seniority,
      job.remote_status,
    ] as (string | null)[]
  ).filter(
    (t): t is string => typeof t === 'string' && t.length > 0 && t !== 'Unspecified',
  )

  return (
    <div
      className={`jc-hover relative flex flex-col gap-2.5 rounded-[10px] p-4 select-none ${onFocus ? 'cursor-pointer' : 'cursor-default'}`}
      style={{ background: '#0F1117' }}
      onClick={onFocus ? () => onFocus(job) : undefined}
      role={onFocus ? 'button' : undefined}
      tabIndex={onFocus ? 0 : undefined}
      onKeyDown={onFocus ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(job) } } : undefined}
    >
      {/* Top shimmer accent line — see .jc-hover:hover .jc-shimmer in globals.css */}
      <div className="jc-shimmer absolute top-0 left-0 right-0 h-px rounded-t-[10px]" />

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

      {/* Row 3 — tags */}
      {tags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {tags.map((t) => (
            <TagPill key={t} label={t} />
          ))}
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
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
            {formatRelativeDate(job.first_seen_at)} · via {job.source}
          </span>
          {score && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setExpanded(v => !v) }}
              className="font-mono text-[10px] rounded px-1.5 py-0.5 transition-colors"
              style={{
                background: expanded ? 'rgba(0,212,255,0.10)' : 'transparent',
                border: '1px solid #252D40',
                color: expanded ? '#00D4FF' : '#6B7A99',
              }}
              aria-expanded={expanded}
              aria-label={expanded ? 'Hide score breakdown' : 'Show score breakdown'}
            >
              {expanded ? '▴ hide' : '▾ details'}
            </button>
          )}
        </div>
        <div
          className="flex items-center gap-1"
          onClick={(e) => e.stopPropagation()}
        >
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
              onClick={(e) => { e.stopPropagation(); handleApply() }}
              className="font-mono text-[10px] font-semibold rounded-[5px] px-3 py-[5px] transition-transform duration-150 hover:scale-[1.03]"
              style={{
                background: '#00D4FF',
                border: '1px solid #00D4FF',
                color: '#000',
              }}
            >
              apply →
            </button>
          )}
        </div>
      </div>

      {/* Inline score breakdown — only when toggled. stopPropagation on the
          wrapper so clicks inside don't trip the card-level focus handler. */}
      {expanded && score && (
        <div onClick={(e) => e.stopPropagation()}>
          <ScoreBreakdownPanel score={score} />
        </div>
      )}
    </div>
  )
}
