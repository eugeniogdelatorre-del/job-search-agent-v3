export function formatSalary(min: number | null, max: number | null): string | null {
  // Audit M13: previously used truthy checks (`!min && !max`), so a
  // range of (0, 200000) returned "$0" because `!0` short-circuited
  // the range branch. Explicit null checks avoid the trap.
  if (min == null && max == null) return null
  const fmt = (n: number) => (n >= 1000 ? `$${Math.round(n / 1000)}k` : `$${n}`)
  if (min != null && max != null && min !== max) return `${fmt(min)}–${fmt(max)}`
  // At this point at least one is non-null; pick the non-null side.
  const v = min ?? max
  return v == null ? null : fmt(v)
}

export function formatRelativeDate(iso: string): string {
  const then = new Date(iso).getTime()
  const now = Date.now()
  // Audit L7: clamp negative deltas to 0 so future-dated rows / clock
  // skew don't print "NaN ago" or "-3m ago".
  const mins = Math.max(0, Math.round((now - then) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 7) return `${days}d ago`
  const weeks = Math.round(days / 7)
  if (weeks < 5) return `${weeks}w ago`
  const months = Math.round(days / 30)
  return `${months}mo ago`
}

export function formatUsd(n: number): string {
  if (n === 0) return '$0.00'
  if (n < 0.01) return `$${n.toFixed(4)}`
  if (n < 1) return `$${n.toFixed(3)}`
  return `$${n.toFixed(2)}`
}
