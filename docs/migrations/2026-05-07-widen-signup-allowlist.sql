-- Widens the signup gate (auth.users INSERT trigger) from a single
-- hard-coded email to a small allowlist. Same trigger /
-- block_unauthorized_signups() function; body changed to test the new
-- row's email against a fixed array literal. Adding more users later
-- is a one-line edit to ARRAY[...] + re-run this migration.
--
-- Audit L2 (2026-05-20): the allowlist is ONLY documented here and in
-- the comment at web/src/app/login/page.tsx:6-9. Keep both in sync when
-- adding or removing users — grep for "block_unauthorized_signups" to
-- find all references.
--
-- Applied 2026-05-07 against project nqevtnhryjnlbzmiojyb via the
-- Supabase MCP tool (migration name: widen_signup_allowlist_to_three_emails).

CREATE OR REPLACE FUNCTION public.block_unauthorized_signups()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO ''
AS $function$
begin
  if new.email != ALL (ARRAY[
    'eugeniogdelatorre@gmail.com',
    'federicowalter11@gmail.com',
    'anamarta.baptista@gmail.com'
  ]::text[]) then
    raise exception 'Signup not allowed for %', new.email;
  end if;
  return new;
end;
$function$;

-- Verify (the function body should match what's above):
--
-- SELECT pg_get_functiondef('public.block_unauthorized_signups()'::regprocedure);
