// SourceHealthTable — dark terminal table. Status dot: healthy=green,
// failed=red. Click any column header to sort by it (toggles asc/desc on
// repeat clicks). Default sort = Live desc (most-productive sources first),
// with failures floating up on ties so dead sources stay visible.
//
// "New today" and "Live" come from the `jobs` table (active rows), NOT
// from sources_health.jobs_found which counts *what the scraper returned*
// (re-includes already-seen jobs each run). The two new columns answer
// the operator-actionable questions: "did this source produce anything
// new for me today?" and "is this source carrying any of my pipeline?"
//
// 2026-05-13: converted to a client component to support per-column sort.
// All data still arrives pre-computed from the server; the sort key/dir
// is the only client-side state.

'use client'

import { useMemo, useState } from 'react'
import { formatRelativeDate } from '@/lib/format'

type HealthRow = {
  source:        string
  run_at:        string
  jobs_found:    number
  success:       boolean
  error_message: string | null
  duration_ms:   number | null
}

type PerSource = Record<string, { new_today: number; live_total: number }>

type DisplayRow = HealthRow & {
  new_today: number
  live_total: number
}

// Column keys that the user can sort by. Order matters — drives the
// header row below.
type SortKey =
  | 'source'
  | 'status'
  | 'new_today'
  | 'live_total'
  | 'latency'
  | 'last_run'
  | 'error'

type SortDir = 'asc' | 'desc'

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'source',     label: 'Source'     },
  { key: 'status',     label: 'Status'     },
  { key: 'new_today',  label: 'New today'  },
  { key: 'live_total', label: 'Live'       },
  { key: 'latency',    label: 'Latency'    },
  { key: 'last_run',   label: 'Last run'   },
  { key: 'error',      label: 'Error'      },
]

// Default sort direction when a column is first clicked.
// Numeric / time columns default to desc (highest first feels right);
// text columns default to asc (alphabetical).
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  source:     'asc',
  status:     'asc',   // 'down' before 'healthy' (failures float up)
  new_today:  'desc',
  live_total: 'desc',
  latency:    'desc',
  last_run:   'desc',
  error:      'asc',
}

// Comparator factory. Always returns a stable comparator (rows with the
// same primary key fall back to source alphabetical so the order doesn't
// shuffle on every render).
function makeComparator(key: SortKey, dir: SortDir) {
  const mult = dir === 'asc' ? 1 : -1
  return (a: DisplayRow, b: DisplayRow) => {
    let av: number | string
    let bv: number | string
    switch (key) {
      case 'source':
        av = a.source.toLowerCase()
        bv = b.source.toLowerCase()
        break
      case 'status':
        // healthy = 1, down = 0 → asc puts down first (failures up).
        av = a.success ? 1 : 0
        bv = b.success ? 1 : 0
        break
      case 'new_today':
        av = a.new_today
        bv = b.new_today
        break
      case 'live_total':
        av = a.live_total
        bv = b.live_total
        break
      case 'latency':
        // null → -Infinity so it always sorts to the bottom of desc.
        av = a.duration_ms ?? -Infinity
        bv = b.duration_ms ?? -Infinity
        break
      case 'last_run':
        // ISO strings sort lexicographically.
        av = a.run_at
        bv = b.run_at
        break
      case 'error': {
        av = (a.error_message ?? '').toLowerCase()
        bv = (b.error_message ?? '').toLowerCase()
        break
      }
    }
    if (av < bv) return -1 * mult
    if (av > bv) return  1 * mult
    // Stable tiebreaker: alphabetical source.
    return a.source.localeCompare(b.source)
  }
}

export function SourceHealthTable({
  rows,
  perSource = {},
}: {
  rows: HealthRow[]
  perSource?: PerSource
}) {
  // Default = Live desc.
  const [sortKey, setSortKey] = useState<SortKey>('live_total')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Latest run per source — drives Status / Latency / Last run / Error.
  // Compare run_at and keep the max so the caller's order doesn't matter.
  // Memoised because input arrays are stable across re-renders.
  const list = useMemo<DisplayRow[]>(() => {
    const latest = new Map<string, HealthRow>()
    for (const r of rows) {
      const cur = latest.get(r.source)
      if (!cur || r.run_at > cur.run_at) latest.set(r.source, r)
    }
    // Union of sources from both `sources_health` and `jobs`: a source can
    // exist in one table but not the other (live jobs but no recent run,
    // or vice-versa).
    const allSources = new Set<string>([
      ...Array.from(latest.keys()),
      ...Object.keys(perSource),
    ])
    return Array.from(allSources).map((source) => {
      const lastRun = latest.get(source)
      const counts  = perSource[source] ?? { new_today: 0, live_total: 0 }
      return {
        source,
        run_at:        lastRun?.run_at        ?? '',
        jobs_found:    lastRun?.jobs_found    ?? 0,
        success:       lastRun?.success       ?? true,
        error_message: lastRun?.error_message ?? null,
        duration_ms:   lastRun?.duration_ms   ?? null,
        new_today:     counts.new_today,
        live_total:    counts.live_total,
      }
    })
  }, [rows, perSource])

  const sorted = useMemo(
    () => [...list].sort(makeComparator(sortKey, sortDir)),
    [list, sortKey, sortDir]
  )

  const failing       = list.filter((r) => !r.success).length
  const totalNewToday = list.reduce((acc, r) => acc + r.new_today, 0)
  const totalLive     = list.reduce((acc, r) => acc + r.live_total, 0)

  // Click handler: same column toggles direction; different column resets
  // to that column's default direction.
  const onHeaderClick = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(DEFAULT_DIR[key])
    }
  }

  if (list.length === 0) {
    return (
      <div
        className="rounded-[10px] p-10 text-center"
        style={{ borderStyle: 'dashed', borderWidth: 1, borderColor: '#252D40' }}
      >
        <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>No scraper runs logged yet.</p>
      </div>
    )
  }

  return (
    <div
      className="rounded-[10px] overflow-hidden"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      {/* Header */}
      <div className="flex items-baseline justify-between px-4 pt-4 pb-3" style={{ borderBottom: '1px solid #1E2330' }}>
        <h2 className="font-heading font-bold text-sm" style={{ color: '#E8ECF0' }}>Source health</h2>
        <p className="font-mono text-[10px]" style={{ color: '#6B7A99' }}>
          {list.length} sources · {failing} failing · {totalNewToday} new today · {totalLive} live total
        </p>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {COLUMNS.map(({ key, label }) => {
                const active = key === sortKey
                const arrow  = active ? (sortDir === 'asc' ? '▲' : '▼') : ''
                return (
                  <th
                    key={key}
                    onClick={() => onHeaderClick(key)}
                    className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider cursor-pointer select-none transition-colors hover:text-[#E8ECF0]"
                    style={{
                      color: active ? '#00D4FF' : '#3A4460',
                      borderBottom: '1px solid #1E2330',
                    }}
                    title={`Sort by ${label}`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {label}
                      {arrow && <span className="text-[8px]">{arrow}</span>}
                    </span>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, idx) => (
              <tr
                key={r.source}
                style={{ borderBottom: idx < sorted.length - 1 ? '1px solid #1E2330' : undefined }}
              >
                <td className="px-4 py-2.5 font-mono text-[11px] max-w-[160px] truncate" style={{ color: '#A0AABB' }}>
                  {r.source}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <div
                      className="rounded-full"
                      style={{ width: 6, height: 6, background: r.success ? '#4ADE80' : '#F87171', flexShrink: 0 }}
                    />
                    <span
                      className="font-mono text-[10px]"
                      style={{ color: r.success ? '#4ADE80' : '#F87171' }}
                    >
                      {r.success ? 'healthy' : 'down'}
                    </span>
                  </div>
                </td>
                {/* New today — first_seen_at >= UTC midnight.
                    Highlighted in cyan when > 0, dim when 0. */}
                <td
                  className="px-4 py-2.5 font-mono text-[11px] tabular-nums"
                  style={{ color: r.new_today > 0 ? '#00D4FF' : '#3A4460' }}
                >
                  {r.new_today > 0 ? `+${r.new_today}` : '0'}
                </td>
                {/* Live total — is_active=true. The "what's actually
                    contributing to my pipeline right now" number. */}
                <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: '#E8ECF0' }}>
                  {r.live_total}
                </td>
                <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: '#6B7A99' }}>
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '—'}
                </td>
                <td className="px-4 py-2.5 font-mono text-[10px]" style={{ color: '#3A4460' }}>
                  {r.run_at ? formatRelativeDate(r.run_at) : '—'}
                </td>
                <td
                  className="px-4 py-2.5 font-mono text-[10px] max-w-[280px] truncate"
                  style={{ color: '#3A4460' }}
                  title={r.error_message ?? ''}
                >
                  {r.error_message ?? ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
