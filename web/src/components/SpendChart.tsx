// SpendChart — MTD AI spend, broken down by operation (classify /
// geo_filter / cv_score) with a cv_score cache-read ratio KPI. Cache
// hit rate is the dominant cost lever per docs/COST_MATH.md — surfacing
// it makes that knob visible instead of buried in spend_tracking rows.
//
// Hand-rolled SVG so we don't pull in a chart library. Dark terminal
// theme matches the rest of /settings.

import { formatUsd } from '@/lib/format'

type SpendRow = {
  run_at:                       string
  operation:                    string
  cost_usd:                     number
  input_tokens?:                number | null
  cache_write_input_tokens?:    number | null
  cached_input_tokens?:         number | null
  output_tokens?:               number | null
}

const OP_COLOR: Record<string, string> = {
  classify:   '#F5A623',  // amber — fixed-cost band
  geo_filter: '#A78BFA',  // violet — small middle band
  cv_score:   '#00D4FF',  // cyan — dominant band, matches the old chart
}
const OP_FALLBACK = '#6B7A99'

function colorFor(op: string): string {
  return OP_COLOR[op] ?? OP_FALLBACK
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
  // ---- KPI rollups by operation ------------------------------------------
  type OpRoll = {
    cost: number
    calls: number
    input: number
    cache_write: number
    cached: number
    output: number
  }
  const byOp = new Map<string, OpRoll>()
  for (const r of rows) {
    const op = r.operation || 'unknown'
    const cur = byOp.get(op) ?? { cost: 0, calls: 0, input: 0, cache_write: 0, cached: 0, output: 0 }
    cur.cost        += Number(r.cost_usd ?? 0)
    cur.calls       += 1
    cur.input       += Number(r.input_tokens ?? 0)
    cur.cache_write += Number(r.cache_write_input_tokens ?? 0)
    cur.cached      += Number(r.cached_input_tokens ?? 0)
    cur.output      += Number(r.output_tokens ?? 0)
    byOp.set(op, cur)
  }
  const opEntries = Array.from(byOp.entries()).sort((a, b) => b[1].cost - a[1].cost)
  const cvScore = byOp.get('cv_score')
  // Housekeeping #2 (2026-05-21): cache_write_input_tokens is now its own
  // column (migration 011). The denominator is the sum of all three Anthropic
  // token buckets: fresh input + cache-write + cache-read. This gives the
  // exact fraction of prompt tokens that were served from the cache.
  const cacheReadPct = cvScore && (cvScore.input + cvScore.cache_write + cvScore.cached) > 0
    ? (cvScore.cached / (cvScore.input + cvScore.cache_write + cvScore.cached)) * 100
    : null

  // ---- Daily stacked bars ------------------------------------------------
  const dayKeys = new Set<string>()
  const opKeys = new Set<string>()
  const byDayOp = new Map<string, Map<string, number>>()
  for (const r of rows) {
    const day = r.run_at.slice(0, 10)
    const op = r.operation || 'unknown'
    dayKeys.add(day)
    opKeys.add(op)
    const dmap = byDayOp.get(day) ?? new Map<string, number>()
    dmap.set(op, (dmap.get(op) ?? 0) + Number(r.cost_usd ?? 0))
    byDayOp.set(day, dmap)
  }
  const sortedDays = Array.from(dayKeys).sort()
  const filled: string[] = []
  if (sortedDays.length > 0) {
    // Audit L16: previously mutated a single Date in-place via setUTCDate
    // inside the for-condition. Worked because toISOString() read the
    // state before the next mutation, but the pattern is brittle. Step
    // through in milliseconds (UTC has no DST so this is exact).
    const firstMs = Date.UTC(
      Number(sortedDays[0].slice(0, 4)),
      Number(sortedDays[0].slice(5, 7)) - 1,
      Number(sortedDays[0].slice(8, 10)),
    )
    const lastDay = sortedDays[sortedDays.length - 1]
    const lastMs = Date.UTC(
      Number(lastDay.slice(0, 4)),
      Number(lastDay.slice(5, 7)) - 1,
      Number(lastDay.slice(8, 10)),
    )
    for (let ms = firstMs; ms <= lastMs; ms += 86_400_000) {
      filled.push(new Date(ms).toISOString().slice(0, 10))
    }
  }
  // Stable op-stack order: smaller bands first so cv_score sits on top.
  const stackOrder = [
    'classify',
    'geo_filter',
    'cv_score',
    ...Array.from(opKeys).filter(o => o !== 'classify' && o !== 'geo_filter' && o !== 'cv_score'),
  ]
  // Day totals, computed via Array.from(...) instead of `for...of map.values()`
  // — Next.js's `tsconfig` target isn't ES2015+downlevelIteration on iterators,
  // so direct `for...of` on a `MapIterator` is a TS2802 build error. The
  // Array.from() form materializes the iterator first, which compiles cleanly.
  const dayTotals = filled.map((d) => {
    const dmap = byDayOp.get(d)
    if (!dmap) return 0
    return Array.from(dmap.values()).reduce((a, b) => a + b, 0)
  })
  const maxDayTotal = Math.max(0.0001, ...dayTotals)

  const W = 600
  const H = 100
  const PADX = 4
  const barCount = Math.max(filled.length, 1)
  const slot = (W - PADX * 2) / barCount
  const barW = Math.max(1, slot * 0.7)
  const barGap = slot - barW

  const stackedBars = filled.map((day, i) => {
    const dmap = byDayOp.get(day)
    const x = PADX + i * slot + barGap / 2
    const segs: { op: string; y: number; h: number; color: string }[] = []
    let yCursor = H
    if (dmap) {
      for (const op of stackOrder) {
        const v = dmap.get(op) ?? 0
        if (v <= 0) continue
        const h = (v / maxDayTotal) * H
        yCursor -= h
        segs.push({ op, y: yCursor, h, color: colorFor(op) })
      }
    }
    return { day, x, segs }
  })

  const pctOfCap = Math.min(100, (mtdUsd / capUsd) * 100)

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
            Classify + geo_filter + CV scoring · Batch API · Haiku 4.5
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

      {/* KPI tiles: top-2 ops by cost + cv_score cache-read % */}
      {opEntries.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {opEntries.slice(0, 2).map(([op, roll]) => (
            <div
              key={op}
              className="rounded-[6px] px-3 py-2"
              style={{ background: '#0A0C12', border: '1px solid #1E2330' }}
            >
              <div className="flex items-center gap-1.5">
                <div
                  className="rounded-sm"
                  style={{ width: 8, height: 8, background: colorFor(op), flexShrink: 0 }}
                />
                <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: '#6B7A99' }}>
                  {op}
                </span>
              </div>
              <div className="font-mono text-sm font-semibold tabular-nums mt-1" style={{ color: '#E8ECF0' }}>
                {formatUsd(roll.cost)}
              </div>
              <div className="font-mono text-[10px] tabular-nums" style={{ color: '#3A4460' }}>
                {roll.calls} call{roll.calls === 1 ? '' : 's'}
              </div>
            </div>
          ))}
          <div
            className="rounded-[6px] px-3 py-2"
            style={{ background: '#0A0C12', border: '1px solid #1E2330' }}
          >
            <span className="font-mono text-[10px] uppercase tracking-wider" style={{ color: '#6B7A99' }}>
              cv_score cache reads
            </span>
            <div className="font-mono text-sm font-semibold tabular-nums mt-1" style={{ color: cacheReadPct === null ? '#3A4460' : '#E8ECF0' }}>
              {cacheReadPct === null ? '—' : `${cacheReadPct.toFixed(0)}%`}
            </div>
            <div className="font-mono text-[10px] tabular-nums" style={{ color: '#3A4460' }}>
              {cacheReadPct === null ? 'no cv_score data' : 'higher = cheaper'}
            </div>
          </div>
        </div>
      )}

      {/* Stacked daily bars */}
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
            {stackedBars.map((bar, barIdx) => {
              const dayTotal = dayTotals[barIdx] ?? 0
              // 2026-05-14: per-bar hover tooltip via native SVG <title>.
              // Hover any bar to see "YYYY-MM-DD — $X.XX (classify $a /
              // geo_filter $b / cv_score $c)". Pure server-rendered, no
              // client JS, no chart library.
              const dmap = byDayOp.get(bar.day)
              const breakdown = dmap
                ? Array.from(dmap.entries())
                    .filter(([, v]) => v > 0)
                    .map(([op, v]) => `${op} ${formatUsd(v)}`)
                    .join(' · ')
                : ''
              const tooltip = breakdown
                ? `${bar.day} — ${formatUsd(dayTotal)} (${breakdown})`
                : `${bar.day} — no spend`
              return (
                <g key={bar.day}>
                  <title>{tooltip}</title>
                  {/* Invisible full-height hit area so the tooltip fires
                      anywhere over the bar's column, not just the
                      coloured stack itself. */}
                  <rect
                    x={bar.x}
                    y={0}
                    width={barW}
                    height={H}
                    fill="transparent"
                  />
                  {bar.segs.map((s, idx) => (
                    <rect
                      key={`${bar.day}-${s.op}-${idx}`}
                      x={bar.x}
                      y={s.y}
                      width={barW}
                      height={Math.max(0.5, s.h)}
                      fill={s.color}
                      opacity={0.85}
                    />
                  ))}
                </g>
              )
            })}
          </svg>
          <div className="flex justify-between font-mono text-[10px] mt-1" style={{ color: '#3A4460' }}>
            <span>{filled[0]}</span>
            <span>max/day: {formatUsd(maxDayTotal)}</span>
            <span>{filled[filled.length - 1]}</span>
          </div>

          {/* Recent-days strip — at-a-glance daily totals for the last 7 UTC
              days, newest on the right. Bars give shape; this gives numbers
              without forcing a tooltip hover. */}
          <div className="mt-3 flex justify-end gap-2 overflow-x-auto pb-1">
            {filled.slice(-7).map((day, i, arr) => {
              const dmap = byDayOp.get(day)
              const total = dmap
                ? Array.from(dmap.values()).reduce((a, b) => a + b, 0)
                : 0
              const isToday = i === arr.length - 1
              return (
                <div
                  key={day}
                  className="rounded-[4px] px-2 py-1 min-w-[64px] text-right"
                  style={{
                    background: isToday ? '#101524' : '#0A0C12',
                    border: '1px solid #1E2330',
                  }}
                  title={`${day} — total ${formatUsd(total)}`}
                >
                  <div className="font-mono text-[9px] uppercase tracking-wider" style={{ color: isToday ? '#00D4FF' : '#3A4460' }}>
                    {isToday ? 'today' : day.slice(5)}
                  </div>
                  <div
                    className="font-mono text-[11px] font-semibold tabular-nums"
                    style={{ color: total > 0 ? '#E8ECF0' : '#3A4460' }}
                  >
                    {total > 0 ? formatUsd(total) : '—'}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div className="flex gap-3 mt-2">
            {opEntries.map(([op]) => (
              <div key={op} className="flex items-center gap-1.5">
                <div
                  className="rounded-sm"
                  style={{ width: 8, height: 8, background: colorFor(op) }}
                />
                <span className="font-mono text-[10px]" style={{ color: '#6B7A99' }}>{op}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
