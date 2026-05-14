-- 2026-05-14 (post-merge fix): restore `jobs_ranked_for_resume` to
-- `language sql` after migration 008's plpgsql wrapper started silently
-- failing in production.
--
-- Symptom: /today, /week, /archive lost their match_score sort. The
-- web component's queryJobs RPC call returned an error, the fallback
-- path (PostgREST select with parent-level sort) ran instead, and
-- match-score-descending was no longer applied.
--
-- Diagnosis: migration 008 changed the function from `language sql` to
-- `language plpgsql` to host a `raise exception` auth check on
-- p_resume_id ownership. In server-component context the raise was
-- caught by supabase-js as a generic error and queryJobs fell through.
--
-- Fix: same query, same composite ORDER BY, same security-invoker
-- behaviour — but the auth check is expressed as a WHERE filter that
-- empty-results-on-fail instead of raising. Three outcomes:
--
--   * Authed owner → resumes row matches auth.uid() → all candidate
--     rows pass the filter → sorted result.
--   * Authed non-owner → resumes row exists but user_id doesn't match
--     → filter fails → empty result (no data leak, no metadata leak
--     via total_count, no fallback path triggered).
--   * Unauthed (service-role direct call) → auth.uid() is null →
--     resumes.user_id = null is false → empty result.
--
-- The data-leak protection from C2 (web/sql/008_rpc_auth_hardening.sql)
-- is preserved; the difference is response shape on auth failure
-- (empty rows + total_count=0 vs raise). RLS on `job_scores` is the
-- belt-and-braces — even if the WHERE filter were removed entirely,
-- the LEFT JOIN to job_scores would return NULLs for foreign resume
-- ids.
--
-- Idempotent: drops then recreates with the new language. Argument
-- list is unchanged so PostgREST callers don't need to change.

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
        where
            -- C2 ownership check restated as a filter: empty result if
            -- the caller doesn't own p_resume_id (or is unauthed).
            exists (
                select 1 from resumes r
                where r.id = p_resume_id
                  and r.user_id = auth.uid()
            )
          and (p_include_rejected
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
