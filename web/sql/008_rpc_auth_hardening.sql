-- 2026-05-14 (Audit C2 + C3): tighten RPC authorisation surface.
--
-- Two issues spotted in the post-incident review:
--
-- C2: ``jobs_ranked_for_resume(p_resume_id, …)`` is ``security invoker``
--     so RLS prevents data leaks, but the RPC itself didn't verify that
--     ``p_resume_id`` belongs to the caller. Any authed user could call
--     the RPC with any resume UUID and observe filter-behaviour signals
--     (e.g. ``total_count`` changes when ``p_match_min`` / ``p_require_scored``
--     are set against a foreign resume).
--
-- C3: ``set_active_resume(p_user_id, p_resume_id)`` is ``security definer``
--     so it bypasses RLS. It already checks the (resume_id, user_id) pair
--     for consistency, but the pattern of trusting a caller-supplied
--     identity argument inside a ``security definer`` function is a
--     latent privilege-escalation hazard — any future call site that
--     forgets the ownership check loses the protection.
--
-- This migration:
--   * Adds an ``auth.uid()`` ownership check at the top of
--     ``jobs_ranked_for_resume`` (C2).
--   * Drops ``p_user_id`` from ``set_active_resume`` and derives the user
--     from ``auth.uid()`` inside the function (C3). The web routes that
--     call this RPC are updated in the same commit to stop passing
--     ``p_user_id``.
--
-- Idempotent: ``create or replace`` plus a defensive ``drop function``
-- for the old C3 signature (parameter list change). Re-running is safe.

-- ── C2: jobs_ranked_for_resume — verify caller owns p_resume_id ──────

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
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
    v_caller uuid := auth.uid();
begin
    -- C2 ownership check: the RPC takes a resume UUID as a free parameter,
    -- so without this check any authed user could probe filter behaviour
    -- against any resume id. RLS on `job_scores` filters the LEFT JOIN
    -- below (foreign scores come back as NULL) so the data itself is safe
    -- — but `total_count` would observably shift under the
    -- `p_match_min` / `p_require_scored` filters, leaking metadata.
    if v_caller is null then
        raise exception 'auth.uid() returned null; this RPC requires an authed session';
    end if;
    if not exists (
        select 1 from resumes
        where resumes.id = p_resume_id
          and resumes.user_id = v_caller
    ) then
        raise exception 'resume not found or not owned by caller';
    end if;

    return query
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
end;
$$;

grant execute on function jobs_ranked_for_resume(
    uuid, int, int, timestamptz,
    text, text, text, text,
    int, text, int, boolean, boolean
) to authenticated;


-- ── C3: set_active_resume — derive user_id from auth.uid() ───────────

-- Drop the old (uuid, uuid) signature first; Postgres won't replace a
-- function whose argument list changes. Idempotent: the IF EXISTS makes
-- re-running safe even after the new signature is the only one present.
drop function if exists set_active_resume(uuid, uuid);

create or replace function set_active_resume(
    p_resume_id uuid
) returns table (id uuid, is_active boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_caller uuid := auth.uid();
begin
    if v_caller is null then
        raise exception 'auth.uid() returned null; cannot activate resume without a session';
    end if;

    -- Same ownership check as before, but with the user derived from the
    -- session token instead of trusted from a client argument. A
    -- compromised or buggy client cannot now activate a resume owned by
    -- another user.
    if not exists (
        select 1 from resumes
        where resumes.id = p_resume_id
          and resumes.user_id = v_caller
    ) then
        raise exception 'resume not found or not owned by caller';
    end if;

    -- Set-wise update: Postgres evaluates the new value of is_active for
    -- each row in a single pass, so the unique partial index that enforces
    -- "at most one is_active=true per user" is never transiently violated.
    update resumes
    set is_active = (resumes.id = p_resume_id)
    where resumes.user_id = v_caller
      and (resumes.is_active = true OR resumes.id = p_resume_id);

    return query
    select resumes.id, resumes.is_active
    from resumes
    where resumes.id = p_resume_id;
end;
$$;

revoke all   on function set_active_resume(uuid) from public;
grant execute on function set_active_resume(uuid) to authenticated;
grant execute on function set_active_resume(uuid) to service_role;
