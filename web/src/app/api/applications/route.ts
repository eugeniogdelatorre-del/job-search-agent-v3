// POST /api/applications     create or return-existing (idempotent on job_id)
// PATCH /api/applications     update status / notes by id
//
// Snapshot fields (job_title_snapshot, company_snapshot, apply_url_snapshot,
// source_snapshot) let the kanban survive the 60-day job retention sweep —
// per plan §1. When status flips to "applied" we auto-fill applied_at if
// the caller didn't send one.

import { NextRequest, NextResponse } from 'next/server'
import { createClient, getCurrentUser } from '@/lib/supabase/server'
import {
  APPLICATION_STATUSES,
  type ApplicationStatus,
} from '@/types/db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type CreateBody = {
  job_id?: string | null
  job_title_snapshot: string
  company_snapshot?: string | null
  apply_url_snapshot?: string | null
  source_snapshot?: string | null
  status?: ApplicationStatus
  notes?: string | null
}

type PatchBody = {
  id: string
  status?: ApplicationStatus
  notes?: string | null
  applied_at?: string | null
}

export async function POST(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let body: CreateBody
  try {
    body = (await req.json()) as CreateBody
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }

  const title = body.job_title_snapshot?.trim()
  if (!title) {
    return NextResponse.json(
      { error: 'job_title_snapshot required' },
      { status: 400 }
    )
  }

  // Audit M11 + N-M2: validate snapshot strings. apply_url_snapshot must
  // be http(s) so a malicious save can't slip `javascript:` / `data:` /
  // `file:` into the kanban — these would fire when the UI later renders
  // them as a bare `<a href>`. Reject URLs that embed credentials
  // (``https://user:pass@host``) so the Referer header doesn't leak them
  // when the kanban link is clicked. Length caps prevent DB bloat.
  const snapshotErrors: string[] = []
  if (title.length > 500) snapshotErrors.push('job_title_snapshot > 500')
  const apply = (body.apply_url_snapshot ?? '').trim()
  if (apply) {
    try {
      const parsed = new URL(apply)
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
        snapshotErrors.push('apply_url_snapshot must be http(s)')
      }
      if (parsed.username || parsed.password) {
        snapshotErrors.push('apply_url_snapshot must not embed credentials')
      }
    } catch {
      snapshotErrors.push('apply_url_snapshot is not a valid URL')
    }
  }
  if (apply.length > 2000) snapshotErrors.push('apply_url_snapshot > 2000')
  if ((body.company_snapshot ?? '').length > 300) snapshotErrors.push('company_snapshot > 300')
  if ((body.source_snapshot ?? '').length > 100) snapshotErrors.push('source_snapshot > 100')
  if ((body.notes ?? '').length > 5000) snapshotErrors.push('notes > 5000')
  if (snapshotErrors.length > 0) {
    return NextResponse.json({ error: snapshotErrors.join('; ') }, { status: 400 })
  }

  const status: ApplicationStatus = body.status ?? 'saved'
  if (!APPLICATION_STATUSES.includes(status)) {
    return NextResponse.json({ error: 'invalid status' }, { status: 400 })
  }

  // Audit H13: race-safe idempotency. Previously this did SELECT then
  // INSERT, and two concurrent saves could both miss the existing row
  // and create duplicates. Now we use INSERT and catch the unique-
  // violation error from the partial unique index defined in
  // web/sql/002_applications_constraints.sql. If that index isn't
  // deployed yet, behavior degrades to the previous (racy) check-and-
  // insert — see the pre-check below.
  //
  // applied_at is no longer stamped here — the BEFORE-UPDATE/INSERT
  // trigger in the same migration handles it deterministically (H14).
  if (body.job_id) {
    // Defence-in-depth pre-check: serves as the only protection in
    // environments where the migration hasn't been applied yet; once
    // the index is in place, the catch below makes this strictly
    // optional.
    const { data: existing } = await supabase
      .from('applications')
      .select('*')
      .eq('user_id', user.id)
      .eq('job_id', body.job_id)
      .maybeSingle()
    if (existing) {
      return NextResponse.json({ application: existing, duplicate: true })
    }
  }

  const { data: inserted, error } = await supabase
    .from('applications')
    .insert({
      user_id: user.id,
      job_id: body.job_id ?? null,
      job_title_snapshot: title,
      company_snapshot: body.company_snapshot ?? null,
      apply_url_snapshot: body.apply_url_snapshot ?? null,
      source_snapshot: body.source_snapshot ?? null,
      status,
      notes: body.notes ?? null,
    })
    .select('*')
    .single()

  if (error) {
    // Postgres unique_violation = 23505. PostgREST exposes it via
    // ``error.code`` on supabase-js. Race-loser: fetch and return the
    // row the race-winner inserted.
    if (error.code === '23505' && body.job_id) {
      // Audit N-H3: PostgREST's SELECT may run on a different connection
      // from the INSERT, so under read-committed the race-winner's row
      // might not be visible yet on the SELECT's connection. Short retry
      // absorbs the lag (~50ms is plenty for Supabase's intra-region
      // pooler latency).
      for (let attempt = 0; attempt < 3; attempt++) {
        if (attempt > 0) await new Promise((r) => setTimeout(r, 50))
        const { data: existing } = await supabase
          .from('applications')
          .select('*')
          .eq('user_id', user.id)
          .eq('job_id', body.job_id)
          .maybeSingle()
        if (existing) {
          return NextResponse.json({ application: existing, duplicate: true })
        }
      }
      // Audit M6 (2026-05-14): after retries we KNOW the row exists
      // (Postgres just told us with 23505) — we just can't see it on
      // this read replica yet. Returning 500 makes the user think the
      // save failed and click again; they'd then get a 200/duplicate
      // and be confused. Return a soft success instead: the user-intent
      // succeeded, the client just needs to refetch to see the row.
      // The 202 status code signals "accepted but not yet visible".
      console.warn(
        '[api/applications] 23505 but re-fetch empty after retries — replication lag',
        { user_id: user.id, job_id: body.job_id },
      )
      return NextResponse.json(
        { duplicate: true, application: null, message: 'saved (refresh to see)' },
        { status: 202 },
      )
    }
    // Audit M6: don't leak PostgREST error internals to clients.
    console.error('[api/applications] insert failed:', error.message, error.code)
    return NextResponse.json({ error: 'insert failed' }, { status: 500 })
  }
  if (!inserted) {
    console.error('[api/applications] insert returned no row')
    return NextResponse.json({ error: 'insert failed' }, { status: 500 })
  }

  // Audit L14: 201 on actual create (REST convention). The duplicate-
  // branch above stays on 200 because the row already existed.
  return NextResponse.json({ application: inserted, duplicate: false }, { status: 201 })
}

export async function DELETE(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  const { searchParams } = new URL(req.url)
  const id = searchParams.get('id')
  if (!id) return NextResponse.json({ error: 'id required' }, { status: 400 })

  const { error } = await supabase
    .from('applications')
    .delete()
    .eq('id', id)
    .eq('user_id', user.id)

  if (error) {
    // Audit N-M1: don't leak PostgREST error message.
    console.error('[api/applications] delete failed:', error.message, error.code)
    return NextResponse.json({ error: 'delete failed' }, { status: 500 })
  }
  return NextResponse.json({ ok: true })
}

export async function PATCH(req: NextRequest) {
  const supabase = await createClient()
  const user = await getCurrentUser()
  if (!user) return NextResponse.json({ error: 'not authenticated' }, { status: 401 })

  let body: PatchBody
  try {
    body = (await req.json()) as PatchBody
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 })
  }
  if (!body.id) {
    return NextResponse.json({ error: 'id required' }, { status: 400 })
  }
  if (body.status && !APPLICATION_STATUSES.includes(body.status)) {
    return NextResponse.json({ error: 'invalid status' }, { status: 400 })
  }

  const update: Record<string, unknown> = {}
  if (typeof body.status !== 'undefined') update.status = body.status
  if (typeof body.notes !== 'undefined') update.notes = body.notes
  // Audit N-H4: do NOT honor client-supplied applied_at on PATCH. The
  // DB trigger (web/sql/002_applications_constraints.sql) auto-stamps
  // applied_at on the first transition into status='applied'. Allowing
  // the client to set or null-out the field would let users back-date,
  // future-date, or erase the audit trail. If a legitimate use case
  // ever arises (manual back-dating after the fact), add it via a
  // separate, deliberate endpoint or a server-side validated path.
  //
  // Previous H14 comment retained for context: stamping in Postgres is
  // atomic per UPDATE and never overwrites an existing stamp.

  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: 'no fields to update' }, { status: 400 })
  }

  const { data: updated, error } = await supabase
    .from('applications')
    .update(update)
    .eq('id', body.id)
    .eq('user_id', user.id)
    .select('*')
    .single()

  if (error || !updated) {
    // Audit M6: don't leak PostgREST internals.
    console.error('[api/applications] patch failed:', error?.message)
    return NextResponse.json({ error: 'update failed' }, { status: 500 })
  }

  return NextResponse.json({ application: updated })
}
