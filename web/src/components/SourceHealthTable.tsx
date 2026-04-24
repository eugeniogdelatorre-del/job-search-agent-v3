// Latest-run-per-source table. We fetch a bounded recent window and
// reduce client-side to the last row per source. Cheap, exact, no
// window functions required.

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { formatRelativeDate } from '@/lib/format'

type HealthRow = {
  source: string
  run_at: string
  jobs_found: number
  success: boolean
  error_message: string | null
  duration_ms: number | null
}

export function SourceHealthTable({ rows }: { rows: HealthRow[] }) {
  // Latest per source. Rows are ordered newest-first by caller.
  const latest = new Map<string, HealthRow>()
  for (const r of rows) {
    if (!latest.has(r.source)) latest.set(r.source, r)
  }
  const list = Array.from(latest.values()).sort((a, b) => {
    // Failures at the top, then by recency.
    if (a.success !== b.success) return a.success ? 1 : -1
    return b.run_at.localeCompare(a.run_at)
  })

  if (list.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        No scraper runs logged yet.
      </div>
    )
  }

  const failing = list.filter((r) => !r.success).length

  return (
    <div className="space-y-2 rounded-lg border bg-card">
      <div className="flex items-baseline justify-between px-4 pt-4">
        <div>
          <h2 className="text-lg font-semibold">Source health</h2>
          <p className="text-xs text-muted-foreground">
            {list.length} sources · {failing} failing
          </p>
        </div>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Source</TableHead>
            <TableHead className="text-right">Jobs</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last run</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead>Error</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {list.map((r) => (
            <TableRow key={r.source}>
              <TableCell className="font-mono text-xs">{r.source}</TableCell>
              <TableCell className="text-right tabular-nums">
                {r.jobs_found}
              </TableCell>
              <TableCell>
                {r.success ? (
                  <Badge variant="outline" className="border-green-500/40 text-green-700 dark:text-green-400">
                    ok
                  </Badge>
                ) : (
                  <Badge variant="outline" className="border-red-500/40 text-red-700 dark:text-red-400">
                    fail
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {formatRelativeDate(r.run_at)}
              </TableCell>
              <TableCell className="text-xs tabular-nums text-muted-foreground">
                {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '—'}
              </TableCell>
              <TableCell className="max-w-[320px] truncate text-xs text-muted-foreground">
                {r.error_message || ''}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
