// Kanban skeleton — 5 empty columns so the nav placement doesn't shift.

export default function ApplyLoading() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <div className="h-7 w-28 animate-pulse rounded bg-muted" />
      <div className="flex gap-3 overflow-x-auto pb-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="flex min-h-[60vh] w-72 shrink-0 animate-pulse flex-col gap-2 rounded-lg border bg-muted/30 p-2"
          >
            <div className="h-4 w-20 rounded bg-muted" />
            {Array.from({ length: 2 }).map((__, j) => (
              <div key={j} className="h-20 rounded bg-muted/60" />
            ))}
          </div>
        ))}
      </div>
    </main>
  )
}
