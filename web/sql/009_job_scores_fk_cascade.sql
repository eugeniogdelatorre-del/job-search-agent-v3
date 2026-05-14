-- 2026-05-14 (Audit H6): ensure job_scores.resume_id has an ON DELETE
-- CASCADE foreign key to resumes.id.
--
-- Why this matters:
--   web/src/app/api/cv/delete/route.ts deletes a resume row by id under
--   RLS. If job_scores rows exist that point at the deleted resume_id,
--   they're orphaned (RLS still allows the owner to read them via the
--   join in jobs_ranked_for_resume but the resumes row no longer
--   exists). The in-flight guard (Audit N-H9 → M7) catches the
--   "deleted while cv_score is running" race, but does nothing about
--   a clean delete with historical job_scores rows still around.
--
-- Two outcomes after this migration:
--   1. Deleting a non-active resume cascades to its job_scores rows —
--      the user explicitly wanted that CV gone, including its history.
--   2. The DB invariant becomes self-enforcing: orphan job_scores
--      rows are no longer reachable.
--
-- Idempotent — checks information_schema before dropping/recreating
-- the constraint so re-running is a no-op. Safe against either of:
--   * FK exists with the wrong ON DELETE rule (drop and recreate)
--   * FK doesn't exist at all (just create)
--   * FK already exists with the correct rule (no-op)

do $$
declare
    v_constraint_name text;
    v_delete_rule     text;
begin
    -- Locate the FK on job_scores.resume_id, if one exists.
    select tc.constraint_name, rc.delete_rule
    into v_constraint_name, v_delete_rule
    from information_schema.table_constraints tc
    join information_schema.key_column_usage kcu
      on kcu.constraint_name = tc.constraint_name
     and kcu.table_schema    = tc.table_schema
    join information_schema.referential_constraints rc
      on rc.constraint_name = tc.constraint_name
     and rc.constraint_schema = tc.table_schema
    where tc.table_schema    = 'public'
      and tc.table_name      = 'job_scores'
      and kcu.column_name    = 'resume_id'
      and tc.constraint_type = 'FOREIGN KEY'
    limit 1;

    if v_constraint_name is null then
        -- No FK at all — create one with CASCADE.
        execute 'alter table public.job_scores
                 add constraint job_scores_resume_id_fkey
                 foreign key (resume_id)
                 references public.resumes (id)
                 on delete cascade';
        raise notice 'created FK job_scores_resume_id_fkey with ON DELETE CASCADE';
    elsif lower(v_delete_rule) <> 'cascade' then
        -- Wrong rule — drop and recreate with CASCADE.
        execute format(
            'alter table public.job_scores drop constraint %I',
            v_constraint_name
        );
        execute 'alter table public.job_scores
                 add constraint job_scores_resume_id_fkey
                 foreign key (resume_id)
                 references public.resumes (id)
                 on delete cascade';
        raise notice 'recreated FK % with ON DELETE CASCADE (was %)',
                     v_constraint_name, v_delete_rule;
    else
        raise notice 'FK % already has ON DELETE CASCADE — no-op', v_constraint_name;
    end if;
end
$$;

-- Clean up any orphan rows that exist BEFORE the FK becomes enforcing.
-- These could only exist if a resume was hard-deleted on prior code
-- paths without the in-flight guard. The DELETE is bounded — only
-- rows whose resume_id no longer matches any resumes.id are touched.
delete from public.job_scores
where resume_id is not null
  and not exists (
      select 1 from public.resumes r where r.id = job_scores.resume_id
  );
