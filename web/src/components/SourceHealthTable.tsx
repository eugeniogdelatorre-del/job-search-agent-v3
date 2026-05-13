// SourceHealthTable — dark terminal table. Status dot: healthy=green,
// failed=red. Sorted by Live count desc (most-productive sources first);
// failures float up on ties so dead sources stay visible at the
// bottom-of-rank instead of disappearing into a sea of zeroes.
//
// "New today" and "Live" come from the `jobs` table (active rows), NOT
// from sources_health.jobs_found which counts *what the scraper returned*
// (re-includes already-seen jobs each run). The two new columns answer
// the operator-actionable questions: "did this source produce anything
// new for me today?" and "is this source carrying any of my pipeline?"

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

export function SourceHealthTable({
  rows,
  perSource = {},
}: {
  rows: HealthRow[]
  perSource?: PerSource
}) {
  // Latest run per source — drives Status / Latency / Last run / Error.
  // Audit L17: compare run_at and keep the max so the caller's order
  // doesn't matter.
  const latest = new Map<string, HealthRow>()
  for (const r of rows) {
    const cur = latest.get(r.source)
    if (!cur || r.run_at > cur.run_at) latest.set(r.source, r)
  }

  // Combine the universe of sources from BOTH `sources_health` and `jobs`
  // — a source can exist in one table but not the other (a source with
  // live jobs but no recent run, or vice-versa). Take the union so
  // neither perspective hides the other.
  const allSources = new Set<string>([
    ...Array.from(latest.keys()),
    ...Object.keys(perSource),
  ])

  const list: DisplayRow[] = Array.from(allSources)
    .map((source) => {
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
    .sort((a, b) => {
      // Primary: Live total desc — most productive sources at the top.
      if (b.live_total !== a.live_total) return b.live_total - a.live_total
      // Secondary: New today desc — sources that fired today float up.
      if (b.new_today !== a.new_today) return b.new_today - a.new_today
      // Tertiary: failing sources float up over silent ones at the same count
      // so dead boards stay visible.
      if (a.success !== b.success) return a.success ? 1 : -1
      return b.run_at.localeCompare(a.run_at)
    })

  const failing = list.filter((r) => !r.success).length
  const totalNewToday   = list.reduce((acc, r) => acc + r.new_today, 0)
  const totalLive       = list.reduce((acc, r) => acc + r.live_total, 0)

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
              {['Source', 'Status', 'New today', 'Live', 'Latency', 'Last run', 'Error'].map((h) => (
                <th
                  key={h}
                  className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider"
                  style={{ color: '#3A4460', borderBottom: '1px solid #1E2330' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.map((r, idx) => (
              <tr
                key={r.source}
                style={{ borderBottom: idx < list.length - 1 ? '1px solid #1E2330' : undefined }}
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
