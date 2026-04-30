-- Phase 2.5 — Geo filter columns.
--
-- Run this BEFORE deploying the geo_filter.py + cv_score.py changes from
-- PR "feat/geo-filter-rollout-and-tune-removal". Both scripts query
-- `geo_filtered`; without these columns they fail silently and produce
-- 0 rows.
--
-- Safe to re-run (IF NOT EXISTS guards).
--
-- Verification:
--   SELECT geo_filtered, geo_reject_reason FROM jobs LIMIT 1;
--   SELECT COUNT(*) FROM jobs WHERE geo_filtered = false;  -- backlog
--
-- Optional cleanup (after the new code is live and stable, ~1 week):
--   DROP TABLE IF EXISTS scoring_config;          -- /tune system removed
--   ALTER TABLE jobs                               -- v3 only used a few keys
--     -- (no destructive job-table changes; scoring_config was the only
--     --  /tune surface area)

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS geo_filtered boolean NOT NULL DEFAULT false;

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS geo_reject_reason text;

CREATE INDEX IF NOT EXISTS jobs_geo_filtered_idx
  ON jobs (geo_filtered, is_active);
