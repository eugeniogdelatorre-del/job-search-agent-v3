-- Audit H13 + H14: data-integrity guards for the applications table.
--
-- H13 (POST idempotency):
--   Without a partial unique index, two concurrent "save this job" clicks
--   create two ``applications`` rows. The check-then-insert TOCTOU in
--   web/src/app/api/applications/route.ts cannot prevent it.
--   Adding the partial unique index lets the route use INSERT … ON
--   CONFLICT semantics (supabase-js: ``.upsert({onConflict: '...'})``)
--   and catch the rare-but-real race deterministically.
--
-- H14 (PATCH applied_at race):
--   The route used to read ``applied_at`` then conditionally write it,
--   leaving a window where two PATCHes ("saved → applied" + "applied →
--   interview") could both miss the stamp. A BEFORE-UPDATE trigger that
--   stamps ``applied_at`` exactly once (on the first transition into
--   status='applied' when applied_at is still null) closes the window in
--   one atomic SQL pass per UPDATE.
--
-- Deployment: paste into Supabase Studio > SQL Editor and run.

-- ── H13: partial unique index on (user_id, job_id) for non-null job_id.
-- Rows linked to a job (the only ones that have idempotency semantics —
-- adhoc/manual entries with job_id NULL can legitimately repeat).
create unique index if not exists applications_user_job_unique
    on applications (user_id, job_id)
    where job_id is not null;

-- ── H14: auto-stamp applied_at on transition into 'applied' if null.
-- Audit N-H4 hardening: only stamp on a true null→applied transition.
-- Previously, an UPDATE that explicitly set applied_at = null while
-- status was already 'applied' would re-stamp to now(), silently
-- overwriting a user-initiated clear.
create or replace function applications_stamp_applied_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if NEW.status = 'applied'
       and NEW.applied_at is null
       and (TG_OP = 'INSERT' or OLD.applied_at is null)
    then
        NEW.applied_at := now();
    end if;
    return NEW;
end;
$$;

drop trigger if exists trg_applications_stamp_applied_at on applications;
create trigger trg_applications_stamp_applied_at
    before insert or update on applications
    for each row
    execute function applications_stamp_applied_at();

-- ── Audit N-H1: bump updated_at on every UPDATE.
-- KanbanBoard's optimistic drag re-sorts by updated_at, but Supabase
-- doesn't auto-touch this column on UPDATE — so the PATCH response
-- carried a stale updated_at and the moved card visually jumped back
-- to its old column position. This trigger pins the timestamp at the
-- DB layer so the optimistic client-side bump matches the server.
create or replace function applications_touch_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    NEW.updated_at := now();
    return NEW;
end;
$$;

drop trigger if exists trg_applications_touch_updated_at on applications;
create trigger trg_applications_touch_updated_at
    before update on applications
    for each row
    execute function applications_touch_updated_at();
