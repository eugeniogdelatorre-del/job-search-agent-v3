// SourceHealthTable — dark terminal table. Status dot: healthy=green,
// failed=red. Failures at top, sorted by recency within groups.

import { formatRelativeDate } from '@/lib/format'

type HealthRow = {
  source:        string
  run_at:        string
  jobs_found:    number
  success:       boolean
  error_message: string | null
  duration_ms:   number | null
}

export function SourceHealthTable({ rows }: { rows: HealthRow[] }) {
  const latest = new Map<string, HealthRow>()
  for (const r of rows) {
    if (!latest.has(r.source)) latest.set(r.source, r)
  }
  const list = Array.from(latest.values()).sort((a, b) => {
    if (a.success !== b.success) return a.success ? 1 : -1
    return b.run_at.localeCompare(a.run_at)
  })

  const failing = list.filter((r) => !r.success).length

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
          {list.length} sources · {failing} failing
        </p>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              {['Source', 'Status', 'Jobs today', 'Latency', 'Last run', 'Error'].map((h) => (
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
                <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: '#E8ECF0' }}>
                  {r.jobs_found}
                </td>
                <td className="px-4 py-2.5 font-mono text-[11px] tabular-nums" style={{ color: '#6B7A99' }}>
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '—'}
                </td>
                <td className="px-4 py-2.5 font-mono text-[10px]" style={{ color: '#3A4460' }}>
                  {formatRelativeDate(r.run_at)}
                </td>
                <td className="px-4 py-2.5 font-mono text-[10px] max-w-[280px] truncate" style={{ color: '#3A4460' }}>
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
