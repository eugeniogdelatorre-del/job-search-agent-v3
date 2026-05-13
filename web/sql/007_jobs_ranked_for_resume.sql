-- 2026-05-13: server-side sort of jobs by the active resume's match_score.
--
-- Background:
--   queryJobs in web/src/lib/jobs-query.ts wanted "ORDER BY match_score
--   DESC NULLS LAST, score_total DESC NULLS LAST, first_seen_at DESC"
--   on the JOIN between `jobs` and `job_scores`. The supabase-js call
--   .order('match_score', { foreignTable: 'job_scores', ... }) sorts the
--   embed array WITHIN each parent row, not the parent rows themselves,
--   so with a LEFT JOIN (rows without a score for the active resume
--   still appear) PostgREST silently fell through to the parent-level
--   keys for the actual row ordering. Symptom: a card with no AI match
--   could appear above an 88%-match card.
--
--   A JS post-fetch reorder fixes /today and /week (no pagination) but
--   breaks /archive across pages — pagination boundaries are drawn
--   server-side on score_total, so page 2 may show a higher match than
--   the bottom of page 1.
--
-- This RPC pushes the LEFT JOIN + composite ORDER BY into Postgres so
-- pagination is globally consistent.
--
-- Returns one row per matching job, plus a `total_count` column equal
-- to count(*) over() on the filtered set. Single round-trip for rows +
-- total instead of two queries.
--
-- Security:
--   security invoker (default). RLS on `jobs` (public read) and
--   `job_scores` (owner-only) is respected. Anonymous callers see only
--   the public jobs view; authed callers see their own scores embedded.
--
-- Idempotent — uses `create or replace` and a matching `drop function`
-- (signature changes are rare; if the parameter list shifts, the drop
-- catches the old signature so create can succeed).

drop function if exists jobs_ranked_for_resume(
    uuid, int, int, timestamptz,
    text, text, text, text,
    int, text, int, boolean, boolean
);

create or replace function jobs_ranked_for_resume(
    p_resume_id       uuid,
    p_offset          int          default 0,
    p_limit           int          default 50,
    p_since           timestamptz  default null,
    p_function        text         default null,
    p_vertical        text         default null,
    p_seniority       text         default null,
    p_remote          text         default null,
    p_salary_floor    int          default null,
    p_q               text         default null,
    p_match_min       int          default null,
    p_require_scored  boolean      default false,
    p_include_rejected boolean     default false
)
returns table (
    -- Mirror the jobs+job_scores embed shape that queryJobs returns.
    id                   uuid,
    title                text,
    company              text,
    location             text,
    remote_status        text,
    salary_min_usd       int,
    salary_max_usd       int,
    salary_source        text,
    description          text,
    apply_url            text,
    source               text,
    source_tier          int,
    source_url           text,
    function_category    text,
    function_confidence  numeric,
    vertical             text,
    seniority            text,
    score_total          int,
    first_seen_at        timestamptz,
    last_seen_at         timestamptz,
    is_active            boolean,
    match_score          int,
    strengths            text[],
    gaps                 text[],
    verdict_one_liner    text,
    score_breakdown_v5   jsonb,
    total_count          bigint
)
language sql
stable
security invoker
set search_path = public
as $$
    with filtered as (
        select
            j.id, j.title, j.company, j.location, j.remote_status,
            j.salary_min_usd, j.salary_max_usd, j.salary_source,
            j.description, j.apply_url, j.source, j.source_tier, j.source_url,
            j.function_category, j.function_confidence, j.vertical, j.seniority,
            j.score_total, j.first_seen_at, j.last_seen_at, j.is_active,
            s.match_score, s.strengths, s.gaps, s.verdict_one_liner,
            s.score_breakdown_v5
        from jobs j
        left join job_scores s
            on s.job_id = j.id
            and s.resume_id = p_resume_id
        where (p_include_rejected
               or (j.is_active and (j.score_breakdown->>'gate_failed') is null))
          and (p_since is null            or j.first_seen_at      >= p_since)
          and (p_function is null         or j.function_category   = p_function)
          and (p_vertical is null         or j.vertical            = p_vertical)
          and (p_seniority is null        or j.seniority           = p_seniority)
          and (p_remote is null           or j.remote_status       = p_remote)
          and (p_salary_floor is null
               or j.salary_max_usd is null
               or j.salary_max_usd >= p_salary_floor)
          and (p_q is null
               or j.title   ilike '%' || p_q || '%'
               or j.company ilike '%' || p_q || '%')
          and (p_match_min is null        or s.match_score         >= p_match_min)
          and (not p_require_scored       or s.match_score is not null)
    )
    select
        f.id, f.title, f.company, f.location, f.remote_status,
        f.salary_min_usd, f.salary_max_usd, f.salary_source,
        f.description, f.apply_url, f.source, f.source_tier, f.source_url,
        f.function_category, f.function_confidence, f.vertical, f.seniority,
        f.score_total, f.first_seen_at, f.last_seen_at, f.is_active,
        f.match_score, f.strengths, f.gaps, f.verdict_one_liner,
        f.score_breakdown_v5,
        count(*) over() as total_count
    from filtered f
    order by
        f.match_score   desc nulls last,
        f.score_total   desc nulls last,
        f.first_seen_at desc
    offset p_offset
    limit  p_limit;
$$;

grant execute on function jobs_ranked_for_resume(
    uuid, int, int, timestamptz,
    text, text, text, text,
    int, text, int, boolean, boolean
) to authenticated;
