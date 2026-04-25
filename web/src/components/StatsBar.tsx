// 5-cell stats bar shown at the top of the Today page.
// Data is computed in the server component and passed as props.

type Props = {
  indexed:  number
  scored:   number
  avgMatch: number | null
  rule70:   number
  saved:    number
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-3 px-4">
      <span
        className="font-mono text-lg font-semibold leading-none"
        style={{ color: '#E8ECF0' }}
      >
        {value}
      </span>
      <span
        className="mt-1 font-mono text-[9px] font-medium uppercase tracking-widest"
        style={{ color: '#6B7A99' }}
      >
        {label}
      </span>
    </div>
  )
}

export function StatsBar({ indexed, scored, avgMatch, rule70, saved }: Props) {
  return (
    <div
      className="grid grid-cols-5 rounded-lg overflow-hidden"
      style={{ background: '#0F1117', border: '1px solid #1E2330' }}
    >
      <Stat value={String(indexed)}             label="indexed"    />
      <div style={{ borderLeft: '1px solid #1E2330' }}>
        <Stat value={String(scored)}            label="scored"     />
      </div>
      <div style={{ borderLeft: '1px solid #1E2330' }}>
        <Stat value={avgMatch != null ? `${avgMatch}%` : '—'} label="avg match" />
      </div>
      <div style={{ borderLeft: '1px solid #1E2330' }}>
        <Stat value={String(rule70)}            label="rule ≥ 70"  />
      </div>
      <div style={{ borderLeft: '1px solid #1E2330' }}>
        <Stat value={String(saved)}             label="saved"      />
      </div>
    </div>
  )
}
