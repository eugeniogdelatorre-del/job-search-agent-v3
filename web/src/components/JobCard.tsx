// A single job posting. Composes:
//   - title / company / location / salary
//   - function / vertical / seniority / remote badges (whichever are present)
//   - MatchBadge (null-tolerant; Phase 6 fills it in)
//   - strengths / gaps preview (first item of each, if present)
//   - Apply link + Save-to-tracker stub (wired in Phase 7)

import { ExternalLink, Bookmark } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { MatchBadge } from '@/components/MatchBadge'
import { formatRelativeDate, formatSalary } from '@/lib/format'
import type { JobWithScore } from '@/types/db'

export function JobCard({ job }: { job: JobWithScore }) {
  const score = job.job_scores?.[0]
  const salary = formatSalary(job.salary_min_usd, job.salary_max_usd)
  const applyHref = job.apply_url ?? job.source_url ?? undefined

  return (
    <Card className="flex flex-col">
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold leading-tight">
              {job.title}
            </h3>
            <p className="mt-1 truncate text-sm text-muted-foreground">
              {job.company ?? 'Unknown company'}
              {job.location ? ` · ${job.location}` : ''}
            </p>
          </div>
          <MatchBadge score={score?.match_score ?? null} />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {job.function_category && (
            <Badge variant="secondary">{job.function_category}</Badge>
          )}
          {job.vertical && <Badge variant="secondary">{job.vertical}</Badge>}
          {job.seniority && job.seniority !== 'Unspecified' && (
            <Badge variant="outline">{job.seniority}</Badge>
          )}
          {job.remote_status && job.remote_status !== 'Unspecified' && (
            <Badge variant="outline">{job.remote_status}</Badge>
          )}
          {salary && <Badge variant="outline">{salary}</Badge>}
          {typeof job.score_total === 'number' && (
            <Badge variant="outline" className="tabular-nums">
              rule: {job.score_total}
            </Badge>
          )}
        </div>

        {score && (score.strengths.length > 0 || score.gaps.length > 0) && (
          <div className="space-y-1 text-xs">
            {score.strengths[0] && (
              <p>
                <span className="font-semibold text-green-700 dark:text-green-400">
                  ✓
                </span>{' '}
                {score.strengths[0]}
              </p>
            )}
            {score.gaps[0] && (
              <p>
                <span className="font-semibold text-red-700 dark:text-red-400">
                  ✗
                </span>{' '}
                {score.gaps[0]}
              </p>
            )}
            {score.verdict_one_liner && (
              <p className="text-muted-foreground italic">
                {score.verdict_one_liner}
              </p>
            )}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-xs text-muted-foreground">
            {formatRelativeDate(job.first_seen_at)} · {job.source}
          </span>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="sm"
              title="Save to tracker (Phase 7)"
              disabled
            >
              <Bookmark className="h-4 w-4" />
            </Button>
            {applyHref && (
              <Button asChild size="sm">
                <a href={applyHref} target="_blank" rel="noopener noreferrer">
                  Apply <ExternalLink className="ml-1 h-3 w-3" />
                </a>
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
