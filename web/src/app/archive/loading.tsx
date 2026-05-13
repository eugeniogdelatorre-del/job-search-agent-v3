// Audit L20: skeleton fallback for the slow `/archive` query. Previously
// `<Suspense fallback={null}>` rendered nothing, producing a blank flash
// between filter changes / page navigation.

export default function ArchiveLoading() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="skeleton" style={{ height: 36, width: 200, borderRadius: 6 }} />
          <div className="skeleton" style={{ height: 11, width: 280, borderRadius: 3 }} />
        </div>
        <div className="skeleton" style={{ height: 32, width: 96, borderRadius: 6 }} />
      </div>

      {/* FilterBar skeleton */}
      <div
        className="rounded-[10px] p-3.5"
        style={{ background: '#0F1117', border: '1px solid #1E2330' }}
      >
        <div className="flex flex-wrap items-center gap-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              className="skeleton"
              style={{ height: 34, width: i === 0 ? 220 : 130, borderRadius: 6 }}
            />
          ))}
        </div>
      </div>

      {/* Table skeleton */}
      <div className="rounded-[10px] overflow-hidden" style={{ background: '#0F1117', border: '1px solid #1E2330' }}>
        <div className="p-3 space-y-2.5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="skeleton" style={{ height: 12, flex: 2.2 }} />
              <div className="skeleton" style={{ height: 12, flex: 1.4 }} />
              <div className="skeleton" style={{ height: 12, flex: 1.4 }} />
              <div className="skeleton" style={{ height: 12, flex: 0.8 }} />
              <div className="skeleton" style={{ height: 20, width: 36, borderRadius: 4 }} />
              <div className="skeleton" style={{ height: 12, flex: 0.6 }} />
            </div>
          ))}
        </div>
      </div>
    </main>
  )
}
