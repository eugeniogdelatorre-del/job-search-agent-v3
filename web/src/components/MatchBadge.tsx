// Match % badge. Three tiers per design spec:
//   ≥ 85 → cyan   |  70–84 → light-cyan  |  < 70 → mid-gray  |  null → dim

export function MatchBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) {
    return (
      <span
        className="inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px] italic"
        style={{
          color: '#3A4460',
          background: '#141820',
          borderColor: '#1E2330',
        }}
      >
        —
      </span>
    )
  }

  const style =
    score >= 85
      ? { color: '#00D4FF', background: 'rgba(0,212,255,0.12)', borderColor: 'rgba(0,212,255,0.4)' }
      : score >= 70
      ? { color: '#67E8F9', background: 'rgba(103,232,249,0.08)', borderColor: 'rgba(103,232,249,0.3)' }
      : { color: '#A0AABB', background: 'rgba(160,170,187,0.08)', borderColor: 'rgba(160,170,187,0.2)' }

  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[11px] font-semibold tabular-nums whitespace-nowrap"
      style={style}
    >
      {score}%
    </span>
  )
}
