// Shared job-query helper used by both JobList (cards) and ArchiveTable.
// Keeps filter/scope/embed semantics in one place.

import { createClient, getCurrentUser } from '@/lib/supabase/server'
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
   * When true, return only rows that have a score for the active CV.
   * Implemented via an INNER join on `job_scores` so the SQL `count`
   * matches the rows actually returned and pagination is correct.
   */
  requireScored?: boolean
  /**
   * Audit P-2 (2026-05-13): debug-only "show what's been excluded by
   * geo_filter / retention / rule-gate". When true, the query
   * skips the ``is_active=true`` and ``gate_failed IS NULL`` filters
   * so the caller can spot-check whether the AI/rule pipeline is
   * being over-aggressive. Bound to ?showRejected=1 on /archive.
   */
  includeRejected?: boolean
}

export type QueryResult = {
  rows: JobWithScore[]
  total: number | null
  error: string | null
}

export async function queryJobs(opts: QueryOpts): Promise<QueryResult> {
  const {
    filters, scopeSinceDays, limit, offset = 0, withCount,
    requireScored = false, includeRejected = false,
  } = opts
  const supabase = await createClient()

  // Audit H11: scope the active-resume lookup explicitly by user_id.
  // RLS already filters resumes by owner, but defence-in-depth — if any
  // future code path uses a service-role client on this connection, RLS
  // would no longer protect us. Always pin to the authed user. Also
  // catches the "no logged-in user" case explicitly instead of relying
  // on RLS returning an empty set.
  const user = await getCurrentUser()
  let activeResumeId: string | null = null
  if (user) {
    const { data: activeResume } = await supabase
      .from('resumes')
      .select('id')
      .eq('user_id', user.id)
      .eq('is_active', true)
      .order('id')
      .limit(1)
      .maybeSingle()
    activeResumeId = activeResume?.id ?? null
  }

  // Audit H10: previously this used a LEFT join + JS post-filter for
  // matchMin/requireScored + JS sort + over-fetch (limit * 3). That broke
  // pagination in three ways:
  //   - `count: 'exact'` returned the unfiltered SQL count, so totals lied
  //     whenever matchMin was active.
  //   - `range(offset, offset + fetchLimit - 1)` over-fetched and then
  //     JS-sliced, so pages N>1 missed rows that JS would have selected
  //     from an earlier window.
  //   - Sort happened after the page boundary was already drawn, so the
  //     server-side "top of page" did not match the JS sort key.
  // Fix: push everything into SQL. Use `!inner` whenever the caller has
  // asked for scored rows, filter match_score in PostgREST, sort on the
  // embed column server-side, and `.range()` exactly over the page.
  const matchMin = typeof filters.matchMin === 'number' ? filters.matchMin : null
  const needsScoredOnly = matchMin !== null || requireScored
  const scoresSelect = needsScoredOnly
    ? 'job_scores!inner(match_score, strengths, gaps, verdict_one_liner, score_breakdown_v5, resume_id)'
    : 'job_scores(match_score, strengths, gaps, verdict_one_liner, score_breakdown_v5, resume_id)'

  let query = supabase
    .from('jobs')
    .select(
      `*, ${scoresSelect}`,
      { count: withCount ? 'exact' : undefined }
    )
  // Audit P-2: skip the active/gate-pass filters when the caller wants
  // to see what would otherwise be excluded.
  if (!includeRejected) {
    query = query
      .eq('is_active', true)
      .is('score_breakdown->>gate_failed', null)
  }

  if (activeResumeId) {
    query = query.eq('job_scores.resume_id', activeResumeId)
  }

  if (matchMin !== null) {
    query = query.gte('job_scores.match_score', matchMin)
  }
  if (requireScored) {
    // !inner guarantees a row; this guarantees the score is non-null
    // (matches the original JS predicate `match_score != null`).
    query = query.not('job_scores.match_score', 'is', null)
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
    // Sanitization for PostgREST `.or()` filter values. The string is
    // interpolated into the or-syntax `title.ilike.%X%,company.ilike.%X%`
    // and ANY of these characters could break out of the value position:
    //   `, ( ) . : \ " '`  — PostgREST or-syntax delimiters/grouping
    //   `% _ *`            — ILIKE wildcards (also denial-of-search risk)
    //   control chars      — header smuggling / URL parser edge cases
    // After stripping we trim and length-cap to 100. If nothing remains
    // we skip the filter rather than build a match-all pattern.
    // eslint-disable-next-line no-control-regex
    const q = filters.q.replace(/[%_*,()\\.:"'\x00-\x1f]/g, '').trim().slice(0, 100)
    if (q) {
      query = query.or(`title.ilike.%${q}%,company.ilike.%${q}%`)
    }
  }

  // Server-side sort mirrors what the JS post-fetch sort used to do:
  //   match_score DESC NULLS LAST → score_total DESC NULLS LAST → first_seen_at DESC.
  // We only order by the embed column when there's an active resume — without
  // one the embedded score is non-deterministic (any historical score may be
  // picked) so applying the sort key is meaningless.
  if (activeResumeId) {
    query = query.order('match_score', {
      foreignTable: 'job_scores',
      ascending: false,
      nullsFirst: false,
    })
  }
  query = query
    .order('score_total', { ascending: false, nullsFirst: false })
    .order('first_seen_at', { ascending: false })
    .range(offset, offset + limit - 1)

  const { data, error, count } = await query
  if (error) return { rows: [], total: null, error: error.message }

  return {
    rows: (data ?? []) as JobWithScore[],
    total: count ?? null,
    error: null,
  }
}
