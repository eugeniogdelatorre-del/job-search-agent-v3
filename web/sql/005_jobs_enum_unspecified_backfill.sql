-- Audit M25: collapse the two ways to express "unknown" into one canonical
-- value across the four enum-style columns on jobs.
--
-- classify.py writes 'Unspecified' as the default; UI code checks for
-- both 'Unspecified' and null in some places, only one in others. After
-- this migration, every column is non-null with default 'Unspecified',
-- so consumer code only needs ONE branch (and the M24 dual-check in
-- JobCard.tsx becomes redundant).
--
-- Deployment: paste into Supabase Studio > SQL Editor. After running,
-- the corresponding `| null` can be safely dropped from the Job type
-- in web/src/types/db.ts (left there for now in case a Supabase replica
-- still serves cached nulls).

-- The UPDATE statements are inherently idempotent (no rows match on
-- second run). The ALTER ... SET DEFAULT statements are idempotent at
-- the SQL level. The ALTER ... SET NOT NULL statements are NOT
-- idempotent (re-running errors with "column is already NOT NULL"),
-- so they're wrapped in DO blocks that check information_schema first.
-- Audit N-H10.

update jobs set remote_status     = 'Unspecified' where remote_status     is null;
update jobs set seniority         = 'Unspecified' where seniority         is null;
update jobs set vertical          = 'Other'       where vertical          is null;
update jobs set function_category = 'Other'       where function_category is null;

alter table jobs
    alter column remote_status     set default 'Unspecified',
    alter column seniority         set default 'Unspecified',
    alter column vertical          set default 'Other',
    alter column function_category set default 'Other';

do $$
declare
    col text;
begin
    foreach col in array array['remote_status', 'seniority', 'vertical', 'function_category']
    loop
        if exists (
            select 1 from information_schema.columns
            where table_schema = 'public'
              and table_name = 'jobs'
              and column_name = col
              and is_nullable = 'YES'
        ) then
            execute format('alter table jobs alter column %I set not null', col);
        end if;
    end loop;
end $$;
