-- Adds the 'stale' status to applications for the auto-archive feature.
-- "Applied" cards with no status change in 30+ days get auto-moved to a
-- Stale column by scraper/stale_apps.py (run inside scrape.yml's retention
-- tail). The user can drag a stale card back to any active column at any
-- time — staling is reversible.
--
-- Applied 2026-05-02 against project nqevtnhryjnlbzmiojyb via the Supabase
-- MCP tool (migration name: add_stale_to_applications_status_check). The
-- schema uses a TEXT column with a CHECK constraint, not a Postgres ENUM
-- — so adding the value means dropping and recreating the constraint.

ALTER TABLE public.applications
  DROP CONSTRAINT applications_status_check;

ALTER TABLE public.applications
  ADD CONSTRAINT applications_status_check
  CHECK (status = ANY (ARRAY[
    'saved'::text,
    'applied'::text,
    'interview'::text,
    'offer'::text,
    'rejected'::text,
    'stale'::text
  ]));

-- Verify (should show all 6 values including 'stale'):
--
-- SELECT pg_get_constraintdef(oid)
--   FROM pg_constraint
--   WHERE conrelid = 'public.applications'::regclass
--     AND conname  = 'applications_status_check';
