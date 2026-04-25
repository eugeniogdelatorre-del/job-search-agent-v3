'use client'

// KanbanCard — dark terminal redesign. Draggable via dnd-kit.
// Background #0A0C10 (darker than column), cyan hover border lift.
// × button to delete/unsave from the tracker.

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ExternalLink, StickyNote, X } from 'lucide-react'
import { formatRelativeDate } from '@/lib/format'
import type { Application } from '@/types/db'

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
      <div
        className="rounded-[8px] p-3 cursor-grab active:cursor-grabbing group"
        style={{
          background:  '#0A0C10',
          border:      '1px solid #1E2330',
          transition:  'border-color 0.18s, box-shadow 0.18s',
        }}
        onMouseEnter={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.borderColor = 'rgba(0,212,255,0.35)'
          el.style.boxShadow   = '0 0 0 1px rgba(0,212,255,0.1)'
        }}
        onMouseLeave={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.borderColor = '#1E2330'
          el.style.boxShadow   = 'none'
        }}
      >
        {/* Drag handle area */}
        <div className="space-y-0.5 mb-2" {...attributes} {...listeners}>
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
