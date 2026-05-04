'use client'

// KanbanBoard — 5-column drag-drop tracker. Column headers get the design-spec
// colored dot + mono label. Cards use the dark KanbanCard component.
// dnd-kit drag-drop and notes dialog logic is unchanged from Phase 7.

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

// Per-column colors and labels per design spec.
// `stale` uses a dim slate dot to read as "they ghosted" — distinct from
// the explicit-no red of `rejected` and from any active-pipeline color.
const COLUMN_CONFIG: Record<ApplicationStatus, { label: string; dot: string }> = {
  saved:     { label: 'Saved',     dot: '#6B7A99' },
  applied:   { label: 'Applied',   dot: '#00D4FF' },
  interview: { label: 'Interview', dot: '#A78BFA' },
  offer:     { label: 'Offer',     dot: '#4ADE80' },
  rejected:  { label: 'Rejected',  dot: '#F87171' },
  stale:     { label: 'Stale',     dot: '#3A4460' },
}

function Column({
  status,
  apps,
  onEdit,
  onDelete,
}: {
  status: ApplicationStatus
  apps: Application[]
  onEdit:   (app: Application) => void
  onDelete: (id: string) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const cfg = COLUMN_CONFIG[status]

  return (
    <div
      ref={setNodeRef}
      className="flex flex-col rounded-[10px] overflow-hidden"
      style={{
        background:  isOver ? '#141820' : '#0F1117',
        border:      `1px solid ${isOver ? '#252D40' : '#1E2330'}`,
        minHeight:   '60vh',
        flex:        '1 1 0',
        minWidth:    200,
        transition:  'background 0.15s, border-color 0.15s',
      }}
    >
      {/* Column header */}
      <div
        className="flex items-center justify-between px-3 py-2.5"
        style={{ borderBottom: '1px solid #1E2330' }}
      >
        <div className="flex items-center gap-2">
          <div
            className="rounded-full"
            style={{ width: 7, height: 7, background: cfg.dot, flexShrink: 0 }}
          />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-wider" style={{ color: '#A0AABB' }}>
            {cfg.label}
          </span>
        </div>
        <span className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
          {apps.length}
        </span>
      </div>

      {/* Cards */}
      <SortableContext
        id={status}
        items={apps.map((a) => a.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-2 p-2">
          {apps.map((app) => (
            <KanbanCard key={app.id} application={app} onEdit={onEdit} onDelete={onDelete} />
          ))}
          {apps.length === 0 && (
            <p className="py-6 text-center font-mono text-[11px]" style={{ color: '#3A4460' }}>
              empty
            </p>
          )}
        </div>
      </SortableContext>
    </div>
  )
}

export function KanbanBoard({ initial }: { initial: Application[] }) {
  const [apps,       setApps]       = useState<Application[]>(initial)
  const [activeId,   setActiveId]   = useState<string | null>(null)
  const [editing,    setEditing]    = useState<Application | null>(null)
  const [notesDraft, setNotesDraft] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } })
  )

  const columns: Record<ApplicationStatus, Application[]> = {
    saved: [], applied: [], interview: [], offer: [], rejected: [], stale: [],
  }
  for (const a of apps) columns[a.status].push(a)

  function onDragStart(ev: DragStartEvent) {
    setActiveId(String(ev.active.id))
  }

  async function onDragEnd(ev: DragEndEvent) {
    setActiveId(null)
    const { active, over } = ev
    if (!over) return
    const appId    = String(active.id)
    const overId   = String(over.id)
    const targetStatus: ApplicationStatus = (APPLICATION_STATUSES as string[]).includes(overId)
      ? (overId as ApplicationStatus)
      : apps.find((a) => a.id === overId)?.status ?? 'saved'
    const moving = apps.find((a) => a.id === appId)
    if (!moving || moving.status === targetStatus) return
    const previousStatus     = moving.status
    const optimisticAppliedAt =
      targetStatus === 'applied' && !moving.applied_at
        ? new Date().toISOString()
        : moving.applied_at
    setApps((curr) =>
      curr.map((a) =>
        a.id === appId ? { ...a, status: targetStatus, applied_at: optimisticAppliedAt } : a
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
      setApps((curr) => curr.map((a) => (a.id === appId ? { ...a, status: previousStatus } : a)))
    }
  }

  async function deleteApp(id: string) {
    const prev = apps
    setApps((curr) => curr.filter((a) => a.id !== id))
    try {
      const res = await fetch(`/api/applications?id=${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error((await res.json()).error ?? 'delete failed')
      toast.success('Removed from tracker')
    } catch (e) {
      toast.error(`Could not remove: ${e instanceof Error ? e.message : 'unknown'}`)
      setApps(prev)
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
      setApps((curr) => curr.map((a) => (a.id === application.id ? application : a)))
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
      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div className="flex gap-3 overflow-x-auto pb-3">
          {APPLICATION_STATUSES.map((s) => (
            <Column key={s} status={s} apps={columns[s]} onEdit={openEdit} onDelete={deleteApp} />
          ))}
        </div>
        <DragOverlay>
          {active ? <KanbanCard application={active} onEdit={() => {}} onDelete={undefined} /> : null}
        </DragOverlay>
      </DndContext>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle style={{ fontFamily: 'var(--font-heading)', color: '#E8ECF0' }}>
              {editing?.job_title_snapshot ?? 'Edit notes'}
            </DialogTitle>
          </DialogHeader>
          <textarea
            value={notesDraft}
            onChange={(e) => setNotesDraft(e.target.value)}
            rows={8}
            placeholder="Notes to yourself…"
            className="w-full rounded-md p-2 text-sm focus-visible:outline-none"
            style={{
              background: '#141820',
              border: '1px solid #252D40',
              color: '#E8ECF0',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)} disabled={savingNotes}>
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
