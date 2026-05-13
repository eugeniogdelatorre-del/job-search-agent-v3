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

  // Pre-compute the search-text sanitisation and date cutoff once so both
  // the RPC and PostgREST paths use identical predicates.
  const scopedCutoff = scopeSinceDays
    ? new Date(Date.now() - scopeSinceDays * 86400e3)
    : null
  const filterCutoff = postedWithinCutoff(filters.postedWithin)
  const cutoff =
    scopedCutoff && filterCutoff
      ? new Date(Math.max(scopedCutoff.getTime(), filterCutoff.getTime()))
      : scopedCutoff ?? filterCutoff
  // Sanitization for the title/company ILIKE search (see PostgREST or-filter
  // notes below). Same regex on both paths so behaviour matches.
  // eslint-disable-next-line no-control-regex
  const qSanitized = filters.q?.replace(/[%_*,()\\.:"'\x00-\x1f]/g, '').trim().slice(0, 100)
  const q = qSanitized && qSanitized.length > 0 ? qSanitized : null
  const matchMin = typeof filters.matchMin === 'number' ? filters.matchMin : null

  // ─────────────────────────────────────────────────────────────────────
  // FAST PATH: active resume → call jobs_ranked_for_resume RPC.
  //
  // The RPC pushes the LEFT-JOIN + composite ORDER BY (match_score DESC
  // NULLS LAST, score_total DESC NULLS LAST, first_seen_at DESC) into
  // Postgres so /archive pagination is globally consistent across pages.
  // The previous PostgREST path could only sort by parent-table columns;
  // see web/sql/007_jobs_ranked_for_resume.sql for the full rationale.
  //
  // Falls back to the PostgREST path below if (a) there's no active
  // resume — the embed-column order is moot anyway — or (b) the RPC call
  // errors (e.g. the migration hasn't been applied yet). The fallback
  // keeps the page rendering on operator machines that are behind on
  // schema deploys.
  // ─────────────────────────────────────────────────────────────────────
  if (activeResumeId) {
    type RpcRow = {
      id: string
      title: string
      company: string | null
      location: string | null
      remote_status: JobWithScore['remote_status']
      salary_min_usd: number | null
      salary_max_usd: number | null
      salary_source: string | null
      description: string | null
      apply_url: string | null
      source: string
      source_tier: number | null
      source_url: string | null
      function_category: JobWithScore['function_category']
      function_confidence: number | null
      vertical: JobWithScore['vertical']
      seniority: JobWithScore['seniority']
      score_total: number | null
      first_seen_at: string
      last_seen_at: string
      is_active: boolean
      match_score: number | null
      strengths: string[] | null
      gaps: string[] | null
      verdict_one_liner: string | null
      score_breakdown_v5: JobWithScore['job_scores'][number]['score_breakdown_v5']
      total_count: number
    }
    const { data, error } = await supabase.rpc('jobs_ranked_for_resume', {
      p_resume_id:        activeResumeId,
      p_offset:           offset,
      p_limit:            limit,
      p_since:            cutoff?.toISOString() ?? null,
      p_function:         filters.function       ?? null,
      p_vertical:         filters.vertical       ?? null,
      p_seniority:        filters.seniority      ?? null,
      p_remote:           filters.remote         ?? null,
      p_salary_floor:     filters.salaryFloor && filters.salaryFloor > 0
                            ? filters.salaryFloor
                            : null,
      p_q:                q,
      p_match_min:        matchMin,
      p_require_scored:   requireScored,
      p_include_rejected: includeRejected,
    })
    if (!error && data) {
      const rpcRows = data as RpcRow[]
      const rows: JobWithScore[] = rpcRows.map((r) => ({
        id: r.id,
        title: r.title,
        company: r.company,
        location: r.location,
        remote_status: r.remote_status,
        salary_min_usd: r.salary_min_usd,
        salary_max_usd: r.salary_max_usd,
        salary_source: r.salary_source,
        description: r.description,
        apply_url: r.apply_url,
        source: r.source,
        source_tier: r.source_tier,
        source_url: r.source_url,
        function_category: r.function_category,
        function_confidence: r.function_confidence,
        vertical: r.vertical,
        seniority: r.seniority,
        score_total: r.score_total,
        first_seen_at: r.first_seen_at,
        last_seen_at: r.last_seen_at,
        is_active: r.is_active,
        job_scores: r.match_score === null && r.score_breakdown_v5 === null
          ? []  // no row in job_scores for this (job, active resume)
          : [{
              match_score:        r.match_score,
              strengths:          r.strengths ?? [],
              gaps:               r.gaps      ?? [],
              verdict_one_liner:  r.verdict_one_liner,
              score_breakdown_v5: r.score_breakdown_v5,
            }],
      }))
      // `total_count` is identical on every row (count(*) over() window).
      // Take it from row 0; for an empty result the count is genuinely 0.
      const total = withCount ? (rpcRows[0]?.total_count ?? 0) : null
      return { rows, total, error: null }
    }
    // RPC errored (most often: function not yet deployed). Log and fall
    // through to the legacy PostgREST path so the page still renders.
    if (error) {
      // eslint-disable-next-line no-console
      console.warn('[queryJobs] RPC fallback:', error.message)
    }
  }

  // ─────────────────────────────────────────────────────────────────────
  // FALLBACK PATH: no active resume, or RPC unavailable.
  //
  // Without a resume there's nothing to sort by `match_score` anyway, so
  // the parent-level keys (`score_total` DESC NULLS LAST → `first_seen_at`
  // DESC) give a sensible order. The historical Audit H10 reasoning still
  // applies here.
  // ─────────────────────────────────────────────────────────────────────
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
  if (q) {
    // Same sanitization the RPC path uses; the variable `q` is pre-cleaned
    // at the top of this function.
    query = query.or(`title.ilike.%${q}%,company.ilike.%${q}%`)
  }

  // Server-side sort. Without an active resume there's no match_score to
  // sort by, so `score_total DESC NULLS LAST → first_seen_at DESC` is the
  // best we can do.
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
