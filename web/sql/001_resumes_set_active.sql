-- Audit H12 fix: atomic CV activation via a Postgres function.
--
-- Replaces the two-step deactivate-then-activate pattern in
-- web/src/app/api/cv/activate/route.ts and web/src/app/api/cv/rescore/route.ts.
-- The previous code had a window where the user had zero active resumes
-- between the two updates; cv_score running concurrently in that window
-- would score against null. This function flips ``is_active`` set-wise
-- in a single statement so the partial unique index
-- ``idx_resumes_one_active_per_user`` is never violated and there's no
-- "no active CV" gap.
--
-- Deployment: paste into Supabase Studio > SQL Editor and run against
-- the project DB. After deployment the web routes call this via
-- ``supabase.rpc('set_active_resume', { ... })``.

create or replace function set_active_resume(
    p_user_id uuid,
    p_resume_id uuid
) returns table (id uuid, is_active boolean)
language plpgsql
security definer
set search_path = public
as $$
begin
    -- Confirm the target resume belongs to the caller. Without this, an
    -- authed user could activate someone else's resume by guessing UUIDs.
    if not exists (
        select 1 from resumes
        where resumes.id = p_resume_id
          and resumes.user_id = p_user_id
    ) then
        raise exception 'resume not found or not owned by user';
    end if;

    -- Set-wise update: Postgres evaluates the new value of is_active for
    -- each row in a single pass, so the unique partial index that enforces
    -- "at most one is_active=true per user" is never transiently violated.
    -- The WHERE clause narrows the rows touched so we don't rewrite every
    -- resume the user owns.
    update resumes
    set is_active = (resumes.id = p_resume_id)
    where resumes.user_id = p_user_id
      and (resumes.is_active = true OR resumes.id = p_resume_id);

    return query
    select resumes.id, resumes.is_active
    from resumes
    where resumes.id = p_resume_id;
end;
$$;

-- Restrict callers to the authenticated session role (the web app's
-- supabase client uses anon/authenticated; service-role can call freely).
revoke all on function set_active_resume(uuid, uuid) from public;
grant execute on function set_active_resume(uuid, uuid) to authenticated;
grant execute on function set_active_resume(uuid, uuid) to service_role;
