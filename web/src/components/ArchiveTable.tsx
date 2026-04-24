// Denser table view used by /archive. 50 rows/page with numeric pagination.

import Link from 'next/link'
import { ExternalLink } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { MatchBadge } from '@/components/MatchBadge'
import { SaveToTrackerButton } from '@/components/SaveToTrackerButton'
import { queryJobs } from '@/lib/jobs-query'
import { formatRelativeDate, formatSalary } from '@/lib/format'
import { filtersToSearchParams, type Filters } from '@/lib/filters'

const PAGE_SIZE = 50

type Props = {
  filters: Filters
  page: number
}

export async function ArchiveTable({ filters, page }: Props) {
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
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        Failed to load jobs: {error}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        No jobs match these filters.
      </div>
    )
  }

  const totalPages = total ? Math.max(1, Math.ceil(total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {total?.toLocaleString() ?? rows.length} total · page {page}/{totalPages}
        </span>
      </div>
      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Function</TableHead>
              <TableHead>Vertical</TableHead>
              <TableHead>Salary</TableHead>
              <TableHead>Match</TableHead>
              <TableHead>Rule</TableHead>
              <TableHead>Seen</TableHead>
              <TableHead className="text-right">Apply</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((job) => {
              const score = job.job_scores?.[0]
              const salary = formatSalary(job.salary_min_usd, job.salary_max_usd)
              const applyHref = job.apply_url ?? job.source_url ?? undefined
              return (
                <TableRow key={job.id}>
                  <TableCell className="max-w-[280px]">
                    <div className="truncate font-medium" title={job.title}>
                      {job.title}
                    </div>
                    {job.location && (
                      <div className="truncate text-xs text-muted-foreground">
                        {job.location}
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[160px] truncate">
                    {job.company ?? '—'}
                  </TableCell>
                  <TableCell>
                    {job.function_category ? (
                      <Badge variant="secondary">{job.function_category}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {job.vertical ? (
                      <Badge variant="outline">{job.vertical}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {salary ?? <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell>
                    <MatchBadge score={score?.match_score ?? null} />
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {job.score_total ?? '—'}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatRelativeDate(job.first_seen_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end">
                      <SaveToTrackerButton
                        job_id={job.id}
                        job_title_snapshot={job.title}
                        company_snapshot={job.company}
                        apply_url_snapshot={applyHref ?? null}
                        source_snapshot={job.source}
                      />
                      {applyHref ? (
                        <Button asChild variant="ghost" size="sm">
                          <a
                            href={applyHref}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
                        </Button>
                      ) : (
                        <span className="px-3 text-muted-foreground">—</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
      <Pagination page={page} totalPages={totalPages} filters={filters} />
    </div>
  )
}

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

  return (
    <div className="flex items-center justify-between">
      <Button variant="outline" size="sm" disabled={!prev} asChild={!!prev}>
        {prev ? <Link href={prev}>← Prev</Link> : <span>← Prev</span>}
      </Button>
      <span className="text-xs text-muted-foreground">
        Page {page} of {totalPages}
      </span>
      <Button variant="outline" size="sm" disabled={!next} asChild={!!next}>
        {next ? <Link href={next}>Next →</Link> : <span>Next →</span>}
      </Button>
    </div>
  )
}
