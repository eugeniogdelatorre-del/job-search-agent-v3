// SpendChart — hand-rolled SVG area chart with cyan stroke + gradient fill.
// Design spec: area chart, cyan 1.5px stroke, linearGradient fill
// rgba(0,212,255,0.2) → rgba(0,212,255,0).

import { formatUsd } from '@/lib/format'

type SpendRow = {
  run_at:    string
  operation: string
  cost_usd:  number
}

export function SpendChart({
  rows,
  capUsd,
  mtdUsd,
}: {
  rows:    SpendRow[]
  capUsd:  number
  mtdUsd:  number
}) {
  // Bucket by UTC calendar day
  const byDay = new Map<string, number>()
  for (const r of rows) {
    const day = r.run_at.slice(0, 10)
    byDay.set(day, (byDay.get(day) ?? 0) + Number(r.cost_usd ?? 0))
  }
  const days = Array.from(byDay.entries()).sort(([a], [b]) => a.localeCompare(b))

  // Fill date gaps
  const filled: Array<[string, number]> = []
  if (days.length > 0) {
    const first = new Date(days[0][0] + 'T00:00:00Z')
    const last  = new Date(days[days.length - 1][0] + 'T00:00:00Z')
    for (let d = new Date(first); d <= last; d.setUTCDate(d.getUTCDate() + 1)) {
      const key = d.toISOString().slice(0, 10)
      filled.push([key, byDay.get(key) ?? 0])
    }
  }

  const maxVal    = Math.max(0.001, ...filled.map(([, v]) => v))
  const pctOfCap  = Math.min(100, (mtdUsd / capUsd) * 100)
  const W = 600
  const H = 100
  const PADX = 4

  // Build SVG path points
  const pts = filled.map(([, v], i) => {
    const x = PADX + (i / Math.max(filled.length - 1, 1)) * (W - PADX * 2)
    const y = H - (v / maxVal) * H
    return { x, y }
  })

  const linePath = pts.length > 1
    ? pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
    : ''

  const areaPath = pts.length > 1
    ? `${linePath} L${pts[pts.length - 1].x.toFixed(1)},${H} L${pts[0].x.toFixed(1)},${H} Z`
    : ''

  return (
    <div
      className="rounded-[10px] p-4 space-y-4"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      {/* Header */}
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="font-heading font-bold text-sm" style={{ color: '#E8ECF0' }}>AI spend (MTD)</h2>
          <p className="font-mono text-[10px] mt-0.5" style={{ color: '#6B7A99' }}>
            Classify + CV scoring · Batch API · Haiku 4.5
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-xl font-semibold tabular-nums" style={{ color: '#E8ECF0' }}>
            {formatUsd(mtdUsd)}
          </div>
          <div className="font-mono text-[10px]" style={{ color: '#6B7A99' }}>
            of {formatUsd(capUsd)} cap
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-1.5 overflow-hidden rounded-full" style={{ background: '#1E2330' }}>
          <div
            className="h-full rounded-full transition-all"
            style={{
              width:      `${pctOfCap}%`,
              background: pctOfCap >= 80 ? '#F87171' : pctOfCap >= 50 ? '#F5A623' : '#4ADE80',
            }}
          />
        </div>
        <div className="flex justify-between font-mono text-[10px]" style={{ color: '#3A4460' }}>
          <span>{pctOfCap.toFixed(1)}% of cap</span>
          <span>{rows.length} calls this month</span>
        </div>
      </div>

      {/* Area chart */}
      {filled.length === 0 ? (
        <p className="py-8 text-center font-mono text-[11px]" style={{ color: '#3A4460' }}>
          No AI calls logged this month yet.
        </p>
      ) : (
        <div>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="w-full"
            style={{ height: 100, display: 'block' }}
          >
            <defs>
              <linearGradient id="cyanFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="rgba(0,212,255,0.2)" />
                <stop offset="100%" stopColor="rgba(0,212,255,0)"   />
              </linearGradient>
            </defs>
            {areaPath && (
              <path d={areaPath} fill="url(#cyanFill)" />
            )}
            {linePath && (
              <path d={linePath} fill="none" stroke="#00D4FF" strokeWidth="1.5" strokeLinejoin="round" />
            )}
          </svg>
          <div className="flex justify-between font-mono text-[10px] mt-1" style={{ color: '#3A4460' }}>
            <span>{filled[0][0]}</span>
            <span>max/day: {formatUsd(maxVal)}</span>
            <span>{filled[filled.length - 1][0]}</span>
          </div>
        </div>
      )}
    </div>
  )
}
