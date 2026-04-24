// One application card inside a kanban column. Draggable via dnd-kit.
// Shows title, company, source, applied_at if set, and an edit button that
// opens a dialog for notes.

'use client'

import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ExternalLink, StickyNote } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { formatRelativeDate } from '@/lib/format'
import type { Application } from '@/types/db'

export function KanbanCard({
  application,
  onEdit,
}: {
  application: Application
  onEdit: (app: Application) => void
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
      <Card className="cursor-grab active:cursor-grabbing">
        <CardContent className="space-y-2 p-3">
          <div
            className="space-y-0.5"
            {...attributes}
            {...listeners}
          >
            <p className="line-clamp-2 text-sm font-medium leading-snug">
              {application.job_title_snapshot}
            </p>
            {application.company_snapshot && (
              <p className="truncate text-xs text-muted-foreground">
                {application.company_snapshot}
              </p>
            )}
          </div>

          <div className="flex items-center justify-between gap-1 text-xs text-muted-foreground">
            <span className="truncate">
              {application.applied_at
                ? `Applied ${formatRelativeDate(application.applied_at)}`
                : application.source_snapshot || ''}
            </span>
            <div className="flex shrink-0 gap-0.5">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={() => onEdit(application)}
                title="Edit notes"
              >
                <StickyNote className="h-3.5 w-3.5" />
              </Button>
              {application.apply_url_snapshot && (
                <Button
                  asChild
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <a
                    href={application.apply_url_snapshot}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="Open posting"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </Button>
              )}
            </div>
          </div>

          {application.notes && (
            <p className="line-clamp-2 rounded bg-muted p-1.5 text-xs text-muted-foreground">
              {application.notes}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
