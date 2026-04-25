// Kanban dark skeleton — 5 empty columns with the design-spec dot headers.
export default function ApplyLoading() {
  const DOTS = ['#6B7A99', '#00D4FF', '#A78BFA', '#4ADE80', '#F87171']
  const LABELS = ['Saved', 'Applied', 'Interview', 'Offer', 'Rejected']
  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <div className="skeleton" style={{ height: 36, width: 120, borderRadius: 6 }} />
      <div className="flex gap-3 overflow-x-auto pb-3">
        {DOTS.map((dot, i) => (
          <div
            key={i}
            className="flex flex-col rounded-[10px] overflow-hidden"
            style={{ background: '#0F1117', border: '1px solid #1E2330', minHeight: '60vh', flex: '1 1 0', minWidth: 200 }}
          >
            <div className="flex items-center justify-between px-3 py-2.5" style={{ borderBottom: '1px solid #1E2330' }}>
              <div className="flex items-center gap-2">
                <div className="rounded-full" style={{ width: 7, height: 7, background: dot }} />
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider" style={{ color: '#A0AABB' }}>
                  {LABELS[i]}
                </span>
              </div>
            </div>
            <div className="p-2 space-y-2">
              {[0, 1].map((j) => (
                <div key={j} className="skeleton rounded-[8px]" style={{ height: 68 }} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  )
}
