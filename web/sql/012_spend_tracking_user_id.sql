-- 012_spend_tracking_user_id (2026-05-21): scope spend rows to their owner.
-- All historical rows get user_id = NULL (they remain visible until
-- the API filter is live; see the nullable default below).
-- RLS policy: each user reads only their own rows.
-- The Python scraper inserts with the service-role key, which bypasses RLS
-- for writes — no change needed on the Python side for the INSERT to work,
-- but we add user_id to the row so reads are filtered correctly.

ALTER TABLE spend_tracking
  ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL;

ALTER TABLE spend_tracking ENABLE ROW LEVEL SECURITY;

-- Allow users to read their own rows. NULLs are invisible (fine — those
-- are pre-migration rows from before the owner was tracked).
DROP POLICY IF EXISTS "Users can read own spend" ON spend_tracking;
CREATE POLICY "Users can read own spend"
  ON spend_tracking FOR SELECT
  USING (auth.uid() = user_id);

-- Service-role bypass: inserts from the Python scraper use the service
-- role key, which skips RLS entirely. No INSERT policy needed.
