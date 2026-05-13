// POST /api/cv/upload
//
// Receives a single PDF in multipart/form-data under field name "file".
// Parses text with pdf-parse, SHA-256 the text for dedup, inserts a
// resumes row owned by the current user. If this is the user's first
// resume, sets is_active=true so cv_score.py has something to reference.
//
// PDF binaries are NEVER persisted (plan §1: "Only parsed text + hash
// retained in DB"). We parse in-memory, throw the bytes away, keep text.

import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'
import { createClient, getCurrentUser } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_BYTES = 5 * 1024 * 1024 // 5 MB
const MAX_CHARS = 40_000 // sanity cap — CVs above this are unusual

export async function POST(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let form: FormData
  try {
    form = await req.formData()
  } catch {
    return NextResponse.json({ error: 'invalid multipart body' }, { status: 400 })
  }

  const file = form.get('file')
  if (!(file instanceof File)) {
    return NextResponse.json({ error: 'file field missing' }, { status: 400 })
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: 'file > 5MB' }, { status: 400 })
  }
  // Client-controlled type/extension is a lie until proven otherwise. Keep
  // these as a cheap early reject for the obvious "wrong tool" cases and
  // re-check with the file's actual magic bytes below.
  const lowerName = (file.name || 'resume.pdf').toLowerCase()
  const isPdf = lowerName.endsWith('.pdf') || file.type === 'application/pdf'
  if (!isPdf) {
    return NextResponse.json({ error: 'PDF only' }, { status: 400 })
  }

  const bytes = new Uint8Array(await file.arrayBuffer())

  // Magic-byte check: a real PDF starts with "%PDF-" (0x25 0x50 0x44 0x46 0x2D).
  // Trusting `file.type`/extension would let a renamed exe / polyglot land in
  // storage; the unpdf parse below would catch most cases, but we want a hard
  // reject *before* spinning up the parser.
  if (
    bytes.length < 5 ||
    bytes[0] !== 0x25 ||
    bytes[1] !== 0x50 ||
    bytes[2] !== 0x44 ||
    bytes[3] !== 0x46 ||
    bytes[4] !== 0x2d
  ) {
    return NextResponse.json(
      { error: 'not a valid PDF (magic byte check failed)' },
      { status: 400 },
    )
  }

  // Strip control chars, path separators, and NULs from the supplied
  // filename before we ever persist it. Length-cap to 255 (typical
  // filesystem limit) so a hostile client can't bloat the DB row.
  // eslint-disable-next-line no-control-regex
  const safeFilename = (file.name || 'resume.pdf')
    .replace(/[\x00-\x1f\x7f\\/]/g, '_')
    .slice(0, 255)

  // Audit M10: hash the bytes BEFORE the expensive pdfjs parse. If the
  // same binary has already been uploaded for this user, short-circuit
  // and return the existing row — saves a multi-second parse on a
  // common drag-drop-twice flow. Falls through to text-hash dedup below
  // for the case where the same text comes in via a re-saved PDF (same
  // resume, slightly different binary).
  //
  // Requires web/sql/003_resumes_bytes_hash.sql to be deployed. If the
  // column isn't present yet the SELECT errors with PGRST204 — we
  // swallow that specifically so the route still works pre-migration.
  const bytes_hash = crypto.createHash('sha256').update(bytes).digest('hex')
  const { data: byHash, error: byHashErr } = await supabase
    .from('resumes')
    .select('id, is_active')
    .eq('user_id', user.id)
    .eq('bytes_hash', bytes_hash)
    .maybeSingle()
  if (byHash) {
    return NextResponse.json({
      resume_id: byHash.id,
      duplicate: true,
      is_active: byHash.is_active,
    })
  }
  // PGRST204 ≈ "column does not exist". Anything else we log and ignore
  // — the text-hash dedup below still catches duplicates, just after
  // paying the parse cost.
  if (byHashErr && byHashErr.code !== 'PGRST204' && byHashErr.code !== '42703') {
    console.warn('[api/cv/upload] bytes_hash lookup non-fatal error:', byHashErr.code, byHashErr.message)
  }

  // unpdf ships a serverless build of pdfjs that doesn't rely on DOM
  // globals (DOMMatrix, Promise.withResolvers). Dynamic import so the
  // wasm/worker glue only loads when an upload actually happens.
  let text: string
  try {
    const { extractText, getDocumentProxy } = await import('unpdf')
    const pdf = await getDocumentProxy(bytes)
    const result = await extractText(pdf, { mergePages: true })
    text = (Array.isArray(result.text) ? result.text.join('\n') : result.text).trim()
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'unknown'
    return NextResponse.json(
      { error: `failed to parse PDF: ${msg}` },
      { status: 400 }
    )
  }

  if (text.length < 100) {
    return NextResponse.json(
      { error: 'parsed text too short — is this a text PDF, not a scan?' },
      { status: 400 }
    )
  }
  const truncated = text.slice(0, MAX_CHARS)
  const text_hash = crypto.createHash('sha256').update(truncated).digest('hex')

  // If the same CV (same hash) was already uploaded by this user, return
  // the existing row rather than spawning a duplicate.
  const { data: existing } = await supabase
    .from('resumes')
    .select('id, is_active')
    .eq('user_id', user.id)
    .eq('text_hash', text_hash)
    .maybeSingle()

  if (existing) {
    return NextResponse.json({
      resume_id: existing.id,
      duplicate: true,
      is_active: existing.is_active,
    })
  }

  // Is this the user's first resume? If so, auto-activate.
  const { count } = await supabase
    .from('resumes')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', user.id)
  const isFirst = (count ?? 0) === 0

  // Try to persist bytes_hash. Falls through gracefully when the column
  // isn't deployed yet (see M10 migration).
  const insertRow: Record<string, unknown> = {
    user_id: user.id,
    filename: safeFilename,
    parsed_text: truncated,
    text_hash,
    bytes_hash,
    char_count: truncated.length,
    is_active: isFirst,
  }
  let { data: inserted, error } = await supabase
    .from('resumes')
    .insert(insertRow)
    .select('id, is_active')
    .single()
  if (error && (error.code === 'PGRST204' || error.code === '42703')) {
    // Column doesn't exist — retry without it.
    delete insertRow.bytes_hash
    ;({ data: inserted, error } = await supabase
      .from('resumes')
      .insert(insertRow)
      .select('id, is_active')
      .single())
  }

  if (error || !inserted) {
    // Audit M6: don't leak PostgREST internals.
    console.error('[api/cv/upload] insert failed:', error?.message, error?.code)
    return NextResponse.json({ error: 'insert failed' }, { status: 500 })
  }

  return NextResponse.json({
    resume_id: inserted.id,
    duplicate: false,
    is_active: inserted.is_active,
  })
}
