-- Audit M23: speed up the `score_breakdown->>'gate_failed' IS NULL`
-- predicate used by every job-listing query in jobs-query.ts. JSON-text
-- extraction has no native index, so the predicate forces a sequential
-- scan as `jobs` grows past ~50k rows. A partial expression index on
-- the JSON path lets PostgREST skip the scan.
--
-- Partial because the only branch we ever care about is
-- ``gate_failed IS NULL`` (jobs that passed the rule-based gates).
-- Indexing those rows alone keeps the index tiny.
--
-- Deployment: paste into Supabase Studio > SQL Editor.

create index if not exists jobs_gate_passed_idx
    on jobs (first_seen_at desc)
    where (score_breakdown ->> 'gate_failed') is null;
