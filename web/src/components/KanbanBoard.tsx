// Five-column kanban: Saved → Applied → Interview → Offer / Rejected.
// Uses dnd-kit for drag-drop. When a card moves to a new column we
// optimistically update local state and PATCH /api/applications.
// Edits (notes text) happen via a dialog launched from KanbanCard.

'use client'

import { useState } from 'react'
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { toast } from 'sonner'
import { KanbanCard } from '@/components/KanbanCard'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  APPLICATION_STATUSES,
  type Application,
  type ApplicationStatus,
} from '@/types/db'

const COLUMN_LABELS: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
}

function Column({
  status,
  apps,
  onEdit,
}: {
  status: ApplicationStatus
  apps: Application[]
  onEdit: (app: Application) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  return (
    <div
      ref={setNodeRef}
      className={`flex min-h-[60vh] w-72 shrink-0 flex-col gap-2 rounded-lg border bg-muted/30 p-2 transition-colors ${
        isOver ? 'bg-muted' : ''
      }`}
    >
      <div className="flex items-center justify-between px-1 pb-1">
        <h3 className="text-sm font-semibold">{COLUMN_LABELS[status]}</h3>
        <span className="text-xs text-muted-foreground">{apps.length}</span>
      </div>
      <SortableContext
        id={status}
        items={apps.map((a) => a.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-2">
          {apps.map((app) => (
            <KanbanCard key={app.id} application={app} onEdit={onEdit} />
          ))}
          {apps.length === 0 && (
            <p className="px-1 py-6 text-center text-xs text-muted-foreground">
              Nothing here
            </p>
          )}
        </div>
      </SortableContext>
    </div>
  )
}

export function KanbanBoard({ initial }: { initial: Application[] }) {
  const [apps, setApps] = useState<Application[]>(initial)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [editing, setEditing] = useState<Application | null>(null)
  const [notesDraft, setNotesDraft] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } })
  )

  const columns: Record<ApplicationStatus, Application[]> = {
    saved: [],
    applied: [],
    interview: [],
    offer: [],
    rejected: [],
  }
  for (const a of apps) columns[a.status].push(a)

  function onDragStart(ev: DragStartEvent) {
    setActiveId(String(ev.active.id))
  }

  async function onDragEnd(ev: DragEndEvent) {
    setActiveId(null)
    const { active, over } = ev
    if (!over) return
    const appId = String(active.id)
    const overId = String(over.id)

    // over.id is either a column id or another card id — normalize to column.
    const targetStatus: ApplicationStatus = (
      APPLICATION_STATUSES as string[]
    ).includes(overId)
      ? (overId as ApplicationStatus)
      : apps.find((a) => a.id === overId)?.status ?? 'saved'

    const moving = apps.find((a) => a.id === appId)
    if (!moving || moving.status === targetStatus) return

    const previousStatus = moving.status
    const optimisticAppliedAt =
      targetStatus === 'applied' && !moving.applied_at
        ? new Date().toISOString()
        : moving.applied_at
    setApps((curr) =>
      curr.map((a) =>
        a.id === appId
          ? { ...a, status: targetStatus, applied_at: optimisticAppliedAt }
          : a
      )
    )

    try {
      const res = await fetch('/api/applications', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ id: appId, status: targetStatus }),
      })
      if (!res.ok) throw new Error((await res.json()).error ?? 'update failed')
      const { application } = (await res.json()) as { application: Application }
      setApps((curr) => curr.map((a) => (a.id === appId ? application : a)))
    } catch (e) {
      toast.error(`Could not move card: ${e instanceof Error ? e.message : 'unknown'}`)
      setApps((curr) =>
        curr.map((a) => (a.id === appId ? { ...a, status: previousStatus } : a))
      )
    }
  }

  function openEdit(app: Application) {
    setEditing(app)
    setNotesDraft(app.notes ?? '')
  }

  async function saveNotes() {
    if (!editing) return
    setSavingNotes(true)
    try {
      const res = await fetch('/api/applications', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ id: editing.id, notes: notesDraft }),
      })
      if (!res.ok) throw new Error((await res.json()).error ?? 'save failed')
      const { application } = (await res.json()) as { application: Application }
      setApps((curr) =>
        curr.map((a) => (a.id === application.id ? application : a))
      )
      setEditing(null)
    } catch (e) {
      toast.error(`Could not save: ${e instanceof Error ? e.message : 'unknown'}`)
    } finally {
      setSavingNotes(false)
    }
  }

  const active = activeId ? apps.find((a) => a.id === activeId) ?? null : null

  return (
    <>
      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <div className="flex gap-3 overflow-x-auto pb-3">
          {APPLICATION_STATUSES.map((s) => (
            <Column key={s} status={s} apps={columns[s]} onEdit={openEdit} />
          ))}
        </div>
        <DragOverlay>
          {active ? (
            <KanbanCard application={active} onEdit={() => {}} />
          ) : null}
        </DragOverlay>
      </DndContext>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editing?.job_title_snapshot ?? 'Edit notes'}
            </DialogTitle>
          </DialogHeader>
          <textarea
            value={notesDraft}
            onChange={(e) => setNotesDraft(e.target.value)}
            rows={8}
            placeholder="Notes to yourself…"
            className="w-full rounded-md border border-input bg-background p-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditing(null)}
              disabled={savingNotes}
            >
              Cancel
            </Button>
            <Button onClick={saveNotes} disabled={savingNotes}>
              {savingNotes ? 'Saving…' : 'Save notes'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
