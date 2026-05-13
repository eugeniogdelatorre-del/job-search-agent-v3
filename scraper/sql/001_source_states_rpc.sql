-- Audit C10 fix: atomic source-state update via Postgres function.
--
-- Replaces the read-modify-write pattern in
-- ``scraper/supabase_client.py::update_source_state``. Calling this RPC
-- holds a row lock for the duration of the increment so two concurrent
-- scrapes hitting the same source cannot under-count consecutive_failures.
--
-- This file is checked in but NOT auto-applied. Deploy by pasting the
-- function definition into Supabase Studio → SQL Editor and running it
-- against the project DB. After deployment, switch
-- ``update_source_state`` to call:
--
--     client.rpc("bump_source_state", {
--         "p_source_name": source_name,
--         "p_success": success,
--         "p_suspend_threshold": SUSPEND_AFTER_CONSECUTIVE_FAILURES,
--     }).execute()
--
-- The current Python path is still safe — H19 ensures suspended_at is
-- preserved — but it remains racy until this RPC is wired up.

create or replace function bump_source_state(
    p_source_name text,
    p_success boolean,
    p_suspend_threshold int
) returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_now timestamptz := now();
    v_current source_states%rowtype;
    v_new_failures int;
    v_was_suspended boolean;
    v_newly_suspended boolean;
begin
    -- Audit N-M4: advisory transaction lock before the SELECT. SELECT
    -- FOR UPDATE doesn't lock anything when 0 rows match (the
    -- first-failure case for a never-before-seen source), so two
    -- concurrent first failures would both INSERT and the ON CONFLICT
    -- branch would resolve to consecutive_failures=1 instead of 2.
    -- pg_advisory_xact_lock serializes by source_name regardless of
    -- whether the row exists yet, and auto-releases at commit.
    perform pg_advisory_xact_lock(hashtext(p_source_name));

    -- Row-level lock: any second caller for the same source_name waits
    -- here until we commit, eliminating the read-modify-write race.
    select * into v_current
    from source_states
    where source_name = p_source_name
    for update;

    if p_success then
        insert into source_states (
            source_name,
            consecutive_failures,
            suspended,
            suspended_at,
            last_success_at,
            updated_at
        )
        values (p_source_name, 0, false, null, v_now, v_now)
        on conflict (source_name) do update set
            consecutive_failures = 0,
            suspended = false,
            suspended_at = null,
            last_success_at = v_now,
            updated_at = v_now;
        return;
    end if;

    -- Failure path.
    v_new_failures := coalesce(v_current.consecutive_failures, 0) + 1;
    v_was_suspended := coalesce(v_current.suspended, false);
    v_newly_suspended := (v_new_failures >= p_suspend_threshold)
                          and not v_was_suspended;

    insert into source_states (
        source_name,
        consecutive_failures,
        suspended,
        suspended_at,
        updated_at
    )
    values (
        p_source_name,
        v_new_failures,
        v_was_suspended or v_newly_suspended,
        case when v_newly_suspended then v_now else v_current.suspended_at end,
        v_now
    )
    on conflict (source_name) do update set
        consecutive_failures = excluded.consecutive_failures,
        suspended = excluded.suspended,
        -- Preserve the existing suspended_at except on the
        -- un-suspended → suspended transition.
        suspended_at = case
            when v_newly_suspended then v_now
            else source_states.suspended_at
        end,
        updated_at = excluded.updated_at;
end;
$$;

-- Tighten exposure: PostgREST exposes any function in the public schema
-- to anon/authenticated by default. This one writes source_states (which
-- has RLS off for the service role), so revoke from anon/authenticated
-- and only allow the service role to call it.
revoke all on function bump_source_state(text, boolean, int) from public;
revoke all on function bump_source_state(text, boolean, int) from anon;
revoke all on function bump_source_state(text, boolean, int) from authenticated;
grant execute on function bump_source_state(text, boolean, int) to service_role;
