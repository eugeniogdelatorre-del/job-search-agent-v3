-- C6 (Supabase security advisor, 2026-05-20): public.schema_migrations had RLS
-- disabled. With RLS off the table was readable by the anon role via PostgREST
-- (SELECT on the public schema is granted to anon by default), exposing the
-- full migration history to unauthenticated callers.
--
-- Fix: enable RLS with no permissive policies. The default-deny means
-- anon/authenticated roles can no longer SELECT from this table via PostgREST.
-- The service-role key used by CI and the Python scraper bypasses RLS entirely,
-- so migration runs and the pipeline are unaffected.
--
-- Applied 2026-05-20 against project nqevtnhryjnlbzmiojyb via the
-- Supabase MCP tool (migration name: enable_rls_schema_migrations).

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- Verify (rowsecurity should be true after applying):
-- SELECT schemaname, tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public' AND tablename = 'schema_migrations';
