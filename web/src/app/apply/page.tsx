// /apply — kanban tracker. NavBar is in layout.tsx.
// Snapshot fields survive 60-day job retention sweep.

import { redirect } from 'next/navigation'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import { KanbanBoard } from '@/components/KanbanBoard'
import type { Application } from '@/types/db'

export const dynamic = 'force-dynamic'

export default async function ApplyPage() {
  const supabase = await createClient()

  // Audit C11 + N-M3: gate on a logged-in user before querying (parity
  // with sibling pages). getCurrentUser() is cached per request so it
  // shares the round-trip with any other call site in this render.
  const user = await getCurrentUser()
  if (!user) redirect('/login')

  const { data, error } = await supabase
    .from('applications')
    .select('*')
    .eq('user_id', user.id)
    .order('updated_at', { ascending: false })

  const apps = (data ?? []) as Application[]

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <div className="flex items-baseline justify-between">
        <div>
          <h1
            className="font-heading font-extrabold"
            style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
          >
            Apply
          </h1>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
            {apps.length} tracked · drag to change status
          </p>
        </div>
      </div>

      {error && (
        <p className="font-mono text-sm" style={{ color: '#F87171' }}>
          Failed to load applications: {error.message}
        </p>
      )}

      {apps.length === 0 ? (
        <div
          className="rounded-[10px] border p-10 text-center"
          style={{ borderStyle: 'dashed', borderColor: '#252D40' }}
        >
          <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>
            nothing saved yet
          </p>
          <p className="mt-1 font-mono text-[11px]" style={{ color: '#3A4460' }}>
            bookmark a job from{' '}
            <a href="/" style={{ color: '#6B7A99', textDecoration: 'underline' }}>Today</a>
            {' '}or{' '}
            <a href="/archive" style={{ color: '#6B7A99', textDecoration: 'underline' }}>Archive</a>
          </p>
        </div>
      ) : (
        <KanbanBoard initial={apps} />
      )}
    </main>
  )
}
