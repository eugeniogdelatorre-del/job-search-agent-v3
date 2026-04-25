// Dark skeleton: spend card + health table.
export default function SettingsLoading() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <div className="space-y-2">
        <div className="skeleton" style={{ height: 36, width: 130, borderRadius: 6 }} />
        <div className="skeleton" style={{ height: 13, width: 200, borderRadius: 4 }} />
      </div>
      <div className="skeleton rounded-[10px]" style={{ height: 240 }} />
      <div className="skeleton rounded-[10px]" style={{ height: 320 }} />
    </main>
  )
}
