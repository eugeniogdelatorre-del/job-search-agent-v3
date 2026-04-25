// ArchiveTable — dense dark terminal table for /archive. 50 rows/page.
// Server component: NO event handlers anywhere in this file.
// Pagination uses Tailwind hover classes instead.

import Link from 'next/link'
import { ExternalLink } from 'lucide-react'
import { MatchBadge } from '@/components/MatchBadge'
import { TagPill } from '@/components/TagPill'
import { SaveToTrackerButton } from '@/components/SaveToTrackerButton'
import { queryJobs } from '@/lib/jobs-query'
import { createClient } from '@/lib/supabase/server'
import { formatRelativeDate, formatSalary } from '@/lib/format'
import { filtersToSearchParams, type Filters } from '@/lib/filters'

const PAGE_SIZE = 50

type Props = { filters: Filters; page: number }

export async function ArchiveTable({ filters, page }: Props) {
  const supabase = createClient()
  const offset = (page - 1) * PAGE_SIZE
  const { rows, total, error } = await queryJobs({
    filters,
    scopeSinceDays: 60,
    limit: PAGE_SIZE,
    offset,
    withCount: true,
  })

  if (error) {
    return (
      <div className="rounded-lg p-4 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
        Failed to load jobs: {error}
      </div>
    )
  }

  // Build job_id → application_id map
  const savedMap = new Map<string, string>()
  const { data: { user } } = await supabase.auth.getUser()
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
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-2">
        <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>No jobs match these filters.</p>
      </div>
    )
  }

  const totalPages = total ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between font-mono text-[10px]" style={{ color: '#3A4460' }}>
        <span>{total?.toLocaleString() ?? rows.length} total · page {page}/{totalPages}</span>
      </div>

      <div className="rounded-[10px] overflow-hidden" style={{ background: '#0F1117', border: '1px solid #1E2330' }}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid #1E2330' }}>
                {['Title', 'Company', 'Tags', 'Salary', 'Match', 'Rule', 'Seen', ''].map((h) => (
                  <th
                    key={h}
                    className="px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wider"
                    style={{ color: '#3A4460' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((job, idx) => {
                const score     = job.job_scores?.[0]
                const salary    = formatSalary(job.salary_min_usd, job.salary_max_usd)
                const applyHref = job.apply_url ?? job.source_url ?? undefined
                const isLast    = idx === rows.length - 1
                return (
                  <tr
                    key={job.id}
                    className="transition-colors hover:bg-[#141820]"
                    style={{ borderBottom: isLast ? undefined : '1px solid #1E2330' }}
                  >
                    {/* Title */}
                    <td className="px-3 py-2.5 max-w-[220px]">
                      <div className="truncate font-heading font-bold text-[12px]" style={{ color: '#E8ECF0' }} title={job.title}>
                        {job.title}
                      </div>
                      {job.location && (
                        <div className="truncate font-mono text-[10px]" style={{ color: '#3A4460' }}>
                          {job.location}
                        </div>
                      )}
                    </td>
                    {/* Company */}
                    <td className="px-3 py-2.5 max-w-[140px]">
                      <span className="truncate font-body text-[12px]" style={{ color: '#A0AABB' }}>
                        {job.company ?? '—'}
                      </span>
                    </td>
                    {/* Tags */}
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap gap-1">
                        {job.function_category && <TagPill label={job.function_category} />}
                        {job.vertical          && <TagPill label={job.vertical} />}
                      </div>
                    </td>
                    {/* Salary */}
                    <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums whitespace-nowrap" style={{ color: '#6B7A99' }}>
                      {salary ?? <span style={{ color: '#3A4460' }}>—</span>}
                    </td>
                    {/* Match */}
                    <td className="px-3 py-2.5">
                      <MatchBadge score={score?.match_score ?? null} />
                    </td>
                    {/* Rule */}
                    <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: '#6B7A99' }}>
                      {job.score_total ?? '—'}
                    </td>
                    {/* Seen */}
                    <td className="px-3 py-2.5 font-mono text-[10px] whitespace-nowrap" style={{ color: '#3A4460' }}>
                      {formatRelativeDate(job.first_seen_at)}
                    </td>
                    {/* Actions */}
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-0.5">
                        <SaveToTrackerButton
                          job_id={job.id}
                          job_title_snapshot={job.title}
                          company_snapshot={job.company}
                          apply_url_snapshot={applyHref ?? null}
                          source_snapshot={job.source}
                          savedApplicationId={savedMap.get(job.id) ?? null}
                        />
                        {applyHref ? (
                          <a
                            href={applyHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-center w-7 h-7 rounded transition-colors text-[#6B7A99] hover:text-[#00D4FF]"
                          >
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        ) : (
                          <span className="w-7" />
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <Pagination page={page} totalPages={totalPages} filters={filters} />
    </div>
  )
}

// Pagination uses only Tailwind classes for hover — no JS event handlers
// (this file has no 'use client', so handlers would crash the server render).
function Pagination({
  page,
  totalPages,
  filters,
}: {
  page: number
  totalPages: number
  filters: Filters
}) {
  if (totalPages <= 1) return null

  const mk = (p: number) => {
    const sp = filtersToSearchParams(filters)
    if (p > 1) sp.set('page', String(p))
    const qs = sp.toString()
    return qs ? `/archive?${qs}` : '/archive'
  }
  const prev = page > 1 ? mk(page - 1) : null
  const next = page < totalPages ? mk(page + 1) : null

  const btnCls =
    'font-mono text-[11px] font-medium rounded px-3.5 py-1.5 transition-colors ' +
    'bg-transparent border border-[#252D40] text-[#6B7A99] ' +
    'hover:text-[#E8ECF0] hover:border-[#6B7A99]'

  const btnDisabled =
    'font-mono text-[11px] font-medium rounded px-3.5 py-1.5 ' +
    'bg-transparent border border-[#1E2330] text-[#3A4460] cursor-default'

  return (
    <div className="flex items-center justify-between">
      {prev ? (
        <Link href={prev} className={btnCls}>← Prev</Link>
      ) : (
        <span className={btnDisabled}>← Prev</span>
      )}
      <span className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
        Page {page} of {totalPages}
      </span>
      {next ? (
        <Link href={next} className={btnCls}>Next →</Link>
      ) : (
        <span className={btnDisabled}>Next →</span>
      )}
    </div>
  )
}
