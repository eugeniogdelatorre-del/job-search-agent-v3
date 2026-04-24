// /resume — CV upload + version list + activate.
//
// Per plan §6 Phase 6: PDF drag-drop, version list table, Activate button.
// Only the parsed text is retained server-side (plan §1).

import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { NavBar } from '@/components/NavBar'
import { ResumeUploader } from '@/components/ResumeUploader'
import { ActivateResumeButton } from '@/components/ActivateResumeButton'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatRelativeDate } from '@/lib/format'

export const dynamic = 'force-dynamic'

type ResumeRow = {
  id: string
  filename: string
  char_count: number | null
  is_active: boolean
  created_at: string
}

export default async function ResumePage() {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data, error } = await supabase
    .from('resumes')
    .select('id, filename, char_count, is_active, created_at')
    .order('created_at', { ascending: false })

  const resumes = (data ?? []) as ResumeRow[]

  return (
    <>
      <NavBar email={user.email} />
      <main className="mx-auto max-w-4xl space-y-6 p-4">
        <div>
          <h1 className="text-xl font-semibold">CV</h1>
          <p className="text-sm text-muted-foreground">
            Upload a PDF résumé. The nightly cv_score workflow uses the
            active version to score jobs against your profile.
          </p>
        </div>

        <ResumeUploader />

        <section>
          <h2 className="mb-2 text-sm font-semibold">Versions</h2>
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              Failed to load: {error.message}
            </div>
          )}
          {!error && resumes.length === 0 && (
            <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              No CVs uploaded yet.
            </div>
          )}
          {resumes.length > 0 && (
            <div className="rounded-lg border bg-card">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>File</TableHead>
                    <TableHead>Chars</TableHead>
                    <TableHead>Uploaded</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resumes.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="max-w-[320px] truncate font-medium">
                        {r.filename}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {r.char_count?.toLocaleString() ?? '—'}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatRelativeDate(r.created_at)}
                      </TableCell>
                      <TableCell>
                        {r.is_active ? (
                          <Badge>Active</Badge>
                        ) : (
                          <Badge variant="outline">Inactive</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        {!r.is_active && (
                          <ActivateResumeButton resumeId={r.id} />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
      </main>
    </>
  )
}
