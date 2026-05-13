'use client'

// KanbanCard — dark terminal redesign. Draggable via dnd-kit.
// Background #0A0C10 (darker than column), cyan hover border lift.
// × button to delete/unsave from the tracker.

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ExternalLink, StickyNote, X } from 'lucide-react'
import type { DraggableAttributes } from '@dnd-kit/core'
import type { SyntheticListenerMap } from '@dnd-kit/core/dist/hooks/utilities'
import { formatRelativeDate } from '@/lib/format'
import type { Application } from '@/types/db'

/**
 * Audit M15: presentational variant of KanbanCard used inside
 * <DragOverlay>. It deliberately does NOT call ``useSortable`` so we
 * don't register a second sortable with the same id as the still-mounted
 * source card — that combination causes dnd-kit to emit duplicate-id
 * warnings and momentarily breaks collision detection.
 */
export function KanbanCardOverlay({ application }: { application: Application }) {
  return (
    <CardInner
      application={application}
      onEdit={() => {}}
      onDelete={undefined}
      dragAttributes={undefined}
      dragListeners={undefined}
    />
  )
}

export function KanbanCard({
  application,
  onEdit,
  onDelete,
}: {
  application: Application
  onEdit:   (app: Application) => void
  onDelete?: (id: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: application.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }

  return (
    <div ref={setNodeRef} style={style}>
      <CardInner
        application={application}
        onEdit={onEdit}
        onDelete={onDelete}
        dragAttributes={attributes}
        dragListeners={listeners}
      />
    </div>
  )
}

function CardInner({
  application,
  onEdit,
  onDelete,
  dragAttributes,
  dragListeners,
}: {
  application: Application
  onEdit:   (app: Application) => void
  onDelete?: (id: string) => void
  dragAttributes?: DraggableAttributes
  dragListeners?: SyntheticListenerMap
}) {
  const isDraggable = !!dragListeners
  return (
    <div>
      <div
        className={`kc-hover rounded-[8px] p-3 ${isDraggable ? 'cursor-grab active:cursor-grabbing' : ''} group`}
        style={{ background: '#0A0C10' }}
      >
        {/* Drag handle area — only this region triggers a drag, so the
            action buttons below stay clickable. */}
        <div className="space-y-0.5 mb-2" {...dragAttributes} {...dragListeners}>
          <p
            className="line-clamp-2 font-heading font-bold text-[13px] leading-snug"
            style={{ color: '#E8ECF0', letterSpacing: '-0.02em' }}
          >
            {application.job_title_snapshot}
          </p>
          {application.company_snapshot && (
            <p className="truncate font-body text-[11px]" style={{ color: '#6B7A99' }}>
              {application.company_snapshot}
            </p>
          )}
        </div>

        {/* Bottom row */}
        <div className="flex items-center justify-between gap-1">
          <span className="truncate font-mono text-[10px]" style={{ color: '#3A4460' }}>
            {application.applied_at
              ? `Applied ${formatRelativeDate(application.applied_at)}`
              : application.source_snapshot || ''}
          </span>
          <div className="flex shrink-0 gap-0.5">
            {/* Notes */}
            <button
              className="flex items-center justify-center w-6 h-6 rounded transition-colors text-[#6B7A99] hover:text-[#A0AABB]"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => onEdit(application)}
              title="Edit notes"
            >
              <StickyNote className="h-3 w-3" />
            </button>
            {/* Open link */}
            {application.apply_url_snapshot && (
              <a
                href={application.apply_url_snapshot}
                target="_blank"
                rel="noopener noreferrer"
                title="Open posting"
                className="flex items-center justify-center w-6 h-6 rounded transition-colors text-[#6B7A99] hover:text-[#A0AABB]"
                onPointerDown={(e) => e.stopPropagation()}
              >
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
            {/* Delete / unsave */}
            {onDelete && (
              <button
                className="flex items-center justify-center w-6 h-6 rounded transition-colors text-[#3A4460] hover:text-[#F87171]"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onDelete(application.id)}
                title="Remove from tracker"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>

        {/* Notes preview */}
        {application.notes && (
          <p
            className="mt-2 line-clamp-2 rounded px-1.5 py-1 font-mono text-[10px] leading-relaxed"
            style={{ background: '#141820', color: '#6B7A99' }}
          >
            {application.notes}
          </p>
        )}
      </div>
    </div>
  )
}
