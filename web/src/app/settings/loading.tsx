// Two-block skeleton: spend chart + source health.

export default function SettingsLoading() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <div className="space-y-2">
        <div className="h-7 w-32 animate-pulse rounded bg-muted" />
        <div className="h-4 w-64 animate-pulse rounded bg-muted/60" />
      </div>
      <div className="h-60 animate-pulse rounded-lg border bg-muted/30" />
      <div className="h-80 animate-pulse rounded-lg border bg-muted/30" />
    </main>
  )
}
