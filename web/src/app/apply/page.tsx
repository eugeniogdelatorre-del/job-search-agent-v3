// /apply — kanban tracker. Snapshot fields mean this page survives
// the 60-day job retention sweep even if the underlying job row is
// gone. We fetch all of the current user's applications (RLS makes
// that automatic) and hand them to a client component for drag-drop.

import { createClient } from '@/lib/supabase/server'
import { KanbanBoard } from '@/components/KanbanBoard'
import type { Application } from '@/types/db'

export const dynamic = 'force-dynamic'

export default async function ApplyPage() {
  const supabase = createClient()
  const { data, error } = await supabase
    .from('applications')
    .select('*')
    .order('updated_at', { ascending: false })

  const apps = (data ?? []) as Application[]

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Apply</h1>
        <p className="text-sm text-muted-foreground">
          {apps.length} tracked · drag to change status
        </p>
      </div>

      {error && (
        <p className="text-sm text-red-600">
          Failed to load applications: {error.message}
        </p>
      )}

      {apps.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
          Nothing saved yet. Bookmark a job from{' '}
          <a href="/" className="underline">
            Today
          </a>{' '}
          or{' '}
          <a href="/archive" className="underline">
            Archive
          </a>{' '}
          to start tracking.
        </div>
      ) : (
        <KanbanBoard initial={apps} />
      )}
    </main>
  )
}
