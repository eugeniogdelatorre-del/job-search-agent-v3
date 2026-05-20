-- H1 (REVIEW.md, 2026-05-20): budget cap-trip alert emails were sent on
-- every subsequent pipeline run for the rest of the month (no de-dup).
-- By end-of-month that's 25+ identical "[job-agent] cv_score stage budget
-- tripped" emails consuming Resend free-tier quota and training the
-- operator to auto-filter them (missing the real next trip).
--
-- Fix: spend_alerts table records when each (month_start, scope, operation)
-- alert has been sent. budget._send_cap_alert checks this table before
-- sending; _mark_alert_sent inserts a row after success. The unique index
-- enforces "at most one alert per (month, scope, operation)" at the DB level
-- as a belt-and-suspenders guard against race conditions on concurrent runs.
--
-- RLS is enabled with no permissive policies — the service-role key used
-- by the Python scraper bypasses RLS. Anonymous reads are blocked.
--
-- Applied 2026-05-20 against project nqevtnhryjnlbzmiojyb via the
-- Supabase MCP tool (migration name: create_spend_alerts_dedup_table).

CREATE TABLE IF NOT EXISTS spend_alerts (
    id         bigserial    PRIMARY KEY,
    month_start timestamptz NOT NULL,
    scope      text         NOT NULL,
    operation  text         NOT NULL,
    alerted_at timestamptz  NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS spend_alerts_month_scope_op
    ON spend_alerts (month_start, scope, operation);

ALTER TABLE spend_alerts ENABLE ROW LEVEL SECURITY;

-- Verify:
-- SELECT table_name, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public' AND table_name = 'spend_alerts';
