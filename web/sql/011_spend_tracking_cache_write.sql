-- 011_spend_tracking_cache_write.sql
-- Housekeeping #2 (2026-05-21): add cache_write_input_tokens column so the
-- cv_score pipeline can log cache-write tokens separately instead of packing
-- them into input_tokens.
--
-- Background (Audit M10 / 2026-05-20): cv_score._log_spend was packing
-- cache_write_tokens into input_tokens because the table had no dedicated
-- column. This meant:
--   * input_tokens was inflated (actual_input + cache_write), misleading
--     any query that tries to understand token breakdown per call.
--   * The cache-read % KPI in SpendChart.tsx computed the same numeric result
--     (the packing coincidentally preserved the ratio) but the underlying
--     columns were semantically wrong.
--
-- After this migration:
--   * input_tokens = genuine fresh input tokens only
--   * cache_write_input_tokens = tokens written into the prompt cache
--   * cached_input_tokens = tokens served from the prompt cache (unchanged)
--
-- The column defaults to 0 so all historical rows stay valid and the column
-- is safe to select before any new cv_score rows are written.

ALTER TABLE spend_tracking
  ADD COLUMN IF NOT EXISTS cache_write_input_tokens integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN spend_tracking.cache_write_input_tokens IS
  'Anthropic cache_creation_input_tokens for this call. '
  'Stored separately from input_tokens so the three buckets '
  '(fresh / cache-write / cache-read) are independently observable.';
