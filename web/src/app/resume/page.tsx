// /resume — CV upload + version list + activate. NavBar is in layout.tsx.

import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { ResumeUploader } from '@/components/ResumeUploader'
import { ActivateResumeButton, RescoreButton } from '@/components/ActivateResumeButton'
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
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data, error } = await supabase
    .from('resumes')
    .select('id, filename, char_count, is_active, created_at')
    .order('created_at', { ascending: false })

  const resumes = (data ?? []) as ResumeRow[]

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-4">
      <div>
        <h1
          className="font-heading font-extrabold"
          style={{ fontSize: 36, color: '#E8ECF0', letterSpacing: '-0.04em', lineHeight: 1.1 }}
        >
          CV
        </h1>
        <p className="mt-1 font-mono text-[11px]" style={{ color: '#6B7A99' }}>
          Upload a PDF — use &quot;Activate &amp; re-score&quot; to switch CVs and kick off scoring immediately
        </p>
      </div>

      <ResumeUploader />

      <section>
        <h2 className="mb-3 font-mono text-[10px] font-medium uppercase tracking-widest" style={{ color: '#3A4460' }}>
          Versions
        </h2>

        {error && (
          <div className="rounded-lg p-3 font-mono text-sm" style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171' }}>
            Failed to load: {error.message}
          </div>
        )}

        {!error && resumes.length === 0 && (
          <div
            className="rounded-[10px] p-8 text-center"
            style={{ borderStyle: 'dashed', borderWidth: 1, borderColor: '#252D40' }}
          >
            <p className="font-mono text-[13px]" style={{ color: '#6B7A99' }}>No CVs uploaded yet.</p>
          </div>
        )}

        {resumes.length > 0 && (
          <div className="flex flex-col gap-2">
            {resumes.map((r) => (
              <div
                key={r.id}
                className="flex items-center gap-3 rounded-[8px] px-4 py-3"
                style={{ background: '#0F1117', border: '1px solid #1E2330' }}
              >
                {/* File icon */}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6B7A99" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>

                {/* Filename */}
                <span className="flex-1 truncate font-mono text-[11px]" style={{ color: '#E8ECF0' }}>
                  {r.filename}
                </span>

                {/* Size + date */}
                <span className="font-mono text-[10px] whitespace-nowrap" style={{ color: '#3A4460' }}>
                  {r.char_count?.toLocaleString() ?? '—'} chars · {formatRelativeDate(r.created_at)}
                </span>

                {/* Status badge / activate / rescore buttons */}
                {r.is_active ? (
                  <div className="flex items-center gap-2">
                    <span
                      className="font-mono text-[10px] font-medium rounded px-2.5 py-1"
                      style={{ background: 'rgba(0,212,255,0.12)', border: '1px solid rgba(0,212,255,0.4)', color: '#00D4FF' }}
                    >
                      active
                    </span>
                    <RescoreButton />
                  </div>
                ) : (
                  <ActivateResumeButton resumeId={r.id} />
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  )
}
