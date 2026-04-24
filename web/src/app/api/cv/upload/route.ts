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
import { createClient } from '@/lib/supabase/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const MAX_BYTES = 5 * 1024 * 1024 // 5 MB
const MAX_CHARS = 40_000 // sanity cap — CVs above this are unusual

export async function POST(req: NextRequest) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
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
  const name = (file.name || 'resume.pdf').toLowerCase()
  const isPdf = name.endsWith('.pdf') || file.type === 'application/pdf'
  if (!isPdf) {
    return NextResponse.json({ error: 'PDF only' }, { status: 400 })
  }

  const bytes = new Uint8Array(await file.arrayBuffer())

  // pdf-parse v2: PDFParse class with getText(). Dynamic import so nothing
  // runs at module-load time.
  let text: string
  try {
    const { PDFParse } = await import('pdf-parse')
    const parser = new PDFParse({ data: bytes })
    try {
      const result = await parser.getText()
      text = (result.text || '').trim()
    } finally {
      await parser.destroy()
    }
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

  const { data: inserted, error } = await supabase
    .from('resumes')
    .insert({
      user_id: user.id,
      filename: file.name || 'resume.pdf',
      parsed_text: truncated,
      text_hash,
      char_count: truncated.length,
      is_active: isFirst,
    })
    .select('id, is_active')
    .single()

  if (error || !inserted) {
    return NextResponse.json(
      { error: `insert failed: ${error?.message ?? 'unknown'}` },
      { status: 500 }
    )
  }

  return NextResponse.json({
    resume_id: inserted.id,
    duplicate: false,
    is_active: inserted.is_active,
  })
}
