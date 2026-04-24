// Daily MTD spend breakdown. No dep — hand-rolled SVG bar chart keeps
// bundle lean and avoids chart-library styling drift. Reads rows as
// returned by /api/spend.

import { formatUsd } from '@/lib/format'

type SpendRow = {
  run_at: string
  operation: string
  cost_usd: number
}

export function SpendChart({
  rows,
  capUsd,
  mtdUsd,
}: {
  rows: SpendRow[]
  capUsd: number
  mtdUsd: number
}) {
  // Bucket by UTC calendar day.
  const byDay = new Map<string, number>()
  for (const r of rows) {
    const day = r.run_at.slice(0, 10) // YYYY-MM-DD
    byDay.set(day, (byDay.get(day) ?? 0) + Number(r.cost_usd ?? 0))
  }
  const days = Array.from(byDay.entries()).sort(([a], [b]) =>
    a.localeCompare(b)
  )

  // Fill gaps so the chart doesn't lie about inactive days.
  const filled: Array<[string, number]> = []
  if (days.length > 0) {
    const first = new Date(days[0][0] + 'T00:00:00Z')
    const last = new Date(days[days.length - 1][0] + 'T00:00:00Z')
    for (let d = new Date(first); d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
      const key = d.toISOString().slice(0, 10)
      filled.push([key, byDay.get(key) ?? 0])
    }
  }

  const maxDaily = Math.max(0.001, ...filled.map(([, v]) => v))
  const pctOfCap = Math.min(100, (mtdUsd / capUsd) * 100)

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-semibold">AI spend (MTD)</h2>
          <p className="text-xs text-muted-foreground">
            Classify + CV scoring · Batch API · Haiku 4.5
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums">
            {formatUsd(mtdUsd)}
          </div>
          <div className="text-xs text-muted-foreground">
            of {formatUsd(capUsd)} hard cap
          </div>
        </div>
      </div>

      {/* Cap progress bar */}
      <div className="space-y-1">
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div
            className={
              'h-full ' +
              (pctOfCap >= 80
                ? 'bg-red-500'
                : pctOfCap >= 50
                  ? 'bg-amber-500'
                  : 'bg-green-500')
            }
            style={{ width: `${pctOfCap}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{pctOfCap.toFixed(1)}% of cap used</span>
          <span>{rows.length} total calls this month</span>
        </div>
      </div>

      {/* Daily bars */}
      {filled.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No AI calls logged this month yet.
        </p>
      ) : (
        <div className="space-y-1">
          <div className="flex items-end gap-0.5" style={{ height: 120 }}>
            {filled.map(([day, v]) => (
              <div
                key={day}
                className="flex-1 rounded-t bg-primary/80"
                style={{
                  height: `${(v / maxDaily) * 100}%`,
                  minHeight: v > 0 ? 2 : 0,
                }}
                title={`${day}: ${formatUsd(v)}`}
              />
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{filled[0][0]}</span>
            <span>max/day: {formatUsd(maxDaily)}</span>
            <span>{filled[filled.length - 1][0]}</span>
          </div>
        </div>
      )}
    </div>
  )
}
