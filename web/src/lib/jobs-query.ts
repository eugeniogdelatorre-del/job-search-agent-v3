// Shared job-query helper used by both JobList (cards) and ArchiveTable.
// Keeps filter/scope/embed semantics in one place.

import { createClient } from '@/lib/supabase/server'
import type { JobWithScore } from '@/types/db'
import type { Filters } from '@/lib/filters'
import { postedWithinCutoff } from '@/lib/filters'

export type QueryOpts = {
  filters: Filters
  scopeSinceDays?: number
  limit: number
  offset?: number
  withCount?: boolean
  /**
   * When true, drop rows whose active-CV `job_scores[0].match_score` is null
   * — i.e. the AI scoring pipeline hasn't reached them yet (or they were
   * marked location-ineligible at score 0).
   *
   * Important: this is a POST-fetch filter. The `total` returned by this
   * function still reflects the SQL-scoped count (active + gate-passed +
   * scope), so the caller can show "scored X / indexed Y" without an
   * extra round-trip.
   */
  requireScored?: boolean
}

export type QueryResult = {
  rows: JobWithScore[]
  total: number | null
  error: string | null
}

export async function queryJobs(opts: QueryOpts): Promise<QueryResult> {
  const { filters, scopeSinceDays, limit, offset = 0, withCount, requireScored = false } = opts
  const supabase = createClient()

  const { data: activeResume } = await supabase
    .from('resumes')
    .select('id')
    .eq('is_active', true)
    .maybeSingle()
  const activeResumeId: string | null = activeResume?.id ?? null

  let query = supabase
    .from('jobs')
    .select(
      '*, job_scores(match_score, strengths, gaps, verdict_one_liner, score_breakdown_v5, resume_id)',
      { count: withCount ? 'exact' : undefined }
    )
    .eq('is_active', true)
    .is('score_breakdown->>gate_failed', null)

  if (activeResumeId) {
    query = query.eq('job_scores.resume_id', activeResumeId)
  }

  const scopedCutoff = scopeSinceDays
    ? new Date(Date.now() - scopeSinceDays * 86400e3)
    : null
  const filterCutoff = postedWithinCutoff(filters.postedWithin)
  const cutoff =
    scopedCutoff && filterCutoff
      ? new Date(Math.max(scopedCutoff.getTime(), filterCutoff.getTime()))
      : scopedCutoff ?? filterCutoff
  if (cutoff) query = query.gte('first_seen_at', cutoff.toISOString())

  if (filters.function) query = query.eq('function_category', filters.function)
  if (filters.vertical) query = query.eq('vertical', filters.vertical)
  if (filters.seniority) query = query.eq('seniority', filters.seniority)
  if (filters.remote) query = query.eq('remote_status', filters.remote)
  if (filters.salaryFloor && filters.salaryFloor > 0) {
    query = query.or(
      `salary_max_usd.gte.${filters.salaryFloor},salary_max_usd.is.null`
    )
  }
  if (filters.q) {
    const q = filters.q.replace(/[%,]/g, '')
    query = query.or(`title.ilike.%${q}%,company.ilike.%${q}%`)
  }

  const fetchLimit = Math.min(500, limit * 3)
  query = query
    .order('first_seen_at', { ascending: false })
    .range(offset, offset + fetchLimit - 1)

  const { data, error, count } = await query
  if (error) return { rows: [], total: null, error: error.message }

  const rows = (data ?? []) as JobWithScore[]

  let filtered =
    typeof filters.matchMin === 'number'
      ? rows.filter(
          (r) =>
            (r.job_scores?.[0]?.match_score ?? -1) >= (filters.matchMin ?? 0)
        )
      : rows

  if (requireScored) {
    filtered = filtered.filter((r) => r.job_scores?.[0]?.match_score != null)
  }

  filtered.sort((a, b) => {
    const am = a.job_scores?.[0]?.match_score ?? -1
    const bm = b.job_scores?.[0]?.match_score ?? -1
    if (bm !== am) return bm - am
    const as = a.score_total ?? -1
    const bs = b.score_total ?? -1
    if (bs !== as) return bs - as
    return (
      new Date(b.first_seen_at).getTime() - new Date(a.first_seen_at).getTime()
    )
  })

  return {
    rows: filtered.slice(0, limit),
    total: count ?? null,
    error: null,
  }
}
