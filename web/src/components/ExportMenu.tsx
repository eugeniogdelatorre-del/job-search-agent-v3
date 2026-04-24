// Small download menu rendered on every list view. Builds a link to
// /api/export with the current filters + scope, and a format chosen
// from a dropdown.

'use client'

import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

type Props = {
  scopeSinceDays: number
  currentSearch: string
}

export function ExportMenu({ scopeSinceDays, currentSearch }: Props) {
  function href(format: 'csv' | 'json' | 'notion') {
    const sp = new URLSearchParams(currentSearch)
    sp.set('format', format)
    sp.set('scopeSinceDays', String(scopeSinceDays))
    return `/api/export?${sp.toString()}`
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download className="mr-1.5 h-4 w-4" /> Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <a href={href('csv')} download>
            CSV
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={href('notion')} download>
            Notion-ready CSV
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={href('json')} download>
            JSON
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
