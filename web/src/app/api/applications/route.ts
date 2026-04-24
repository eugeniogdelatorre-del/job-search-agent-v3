// POST /api/applications     create or return-existing (idempotent on job_id)
// PATCH /api/applications     update status / notes by id
//
// Snapshot fields (job_title_snapshot, company_snapshot, apply_url_snapshot,
// source_snapshot) let the kanban survive the 60-day job retention sweep —
// per plan §1. When status flips to "applied" we auto-fill applied_at if
// the caller didn't send one.

import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
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
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
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

  const status: ApplicationStatus = body.status ?? 'saved'
  if (!APPLICATION_STATUSES.includes(status)) {
    return NextResponse.json({ error: 'invalid status' }, { status: 400 })
  }

  // If the user already saved this job, just return it — no dupes.
  if (body.job_id) {
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

  const applied_at = status === 'applied' ? new Date().toISOString() : null

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
      applied_at,
      notes: body.notes ?? null,
    })
    .select('*')
    .single()

  if (error || !inserted) {
    return NextResponse.json(
      { error: `insert failed: ${error?.message ?? 'unknown'}` },
      { status: 500 }
    )
  }

  return NextResponse.json({ application: inserted, duplicate: false })
}

export async function PATCH(req: NextRequest) {
  const supabase = createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
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
  if (typeof body.status !== 'undefined') {
    update.status = body.status
    // First time we see status === 'applied', stamp applied_at if the
    // caller didn't send one explicitly. We only stamp; we don't clobber
    // an earlier applied_at when the user moves forward to interview.
    if (body.status === 'applied' && typeof body.applied_at === 'undefined') {
      const { data: current } = await supabase
        .from('applications')
        .select('applied_at')
        .eq('id', body.id)
        .eq('user_id', user.id)
        .maybeSingle()
      if (current && !current.applied_at) {
        update.applied_at = new Date().toISOString()
      }
    }
  }
  if (typeof body.notes !== 'undefined') update.notes = body.notes
  if (typeof body.applied_at !== 'undefined') update.applied_at = body.applied_at

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
    return NextResponse.json(
      { error: `update failed: ${error?.message ?? 'unknown'}` },
      { status: 500 }
    )
  }

  return NextResponse.json({ application: updated })
}
