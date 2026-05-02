"""Auto-archive stale Kanban cards.

Applications sitting in `applied` with no row update for STALE_AFTER_DAYS
(default 30) drift to `stale` so the active board reflects what actually
needs attention. The user can drag a stale card back to any active column
at any time — staling is reversible and silent (no email).

Why `updated_at` and not a dedicated `last_status_change_at` column:

- The applications table already auto-bumps `updated_at` on every UPDATE
  (Supabase default). Notes edits also bump it, which is desirable —
  editing notes on a card means you're still thinking about that
  application, so the stale clock should reset.
- Adding a separate column would require schema + API plumbing for one
  semantic that `updated_at` already gives us.

Pipeline (called from scrape.py's retention tail):

    1. SELECT id, user_id, status, updated_at
       FROM applications
       WHERE status = 'applied'
         AND updated_at < now() - interval '30 days'
    2. UPDATE matched rows: status = 'stale'
       (Supabase auto-bumps updated_at, which becomes the "moved to stale"
       timestamp.)
    3. Return the count for logging.

Idempotent — re-running on already-stale rows is a no-op (status filter
excludes them).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scraper import supabase_client
else:
    from . import supabase_client

STALE_AFTER_DAYS = 30


def run(client, *, stale_after_days: int = STALE_AFTER_DAYS) -> int:
    """Move Applied → Stale for cards untouched for `stale_after_days`.

    Returns the number of rows transitioned. Fail-soft: any error is
    logged and we return 0 so the surrounding scrape pipeline keeps
    going. We'd rather have stale cards stick around for a day than
    have a Supabase blip take down the scrape.
    """
    if client is None:
        return 0
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=stale_after_days)
    ).isoformat()
    try:
        resp = (
            client.table("applications")
            .update({"status": "stale"})
            .eq("status", "applied")
            .lt("updated_at", cutoff_iso)
            .execute()
        )
        n = len(resp.data) if getattr(resp, "data", None) else 0
        print(
            f"  [supabase] auto-staled {n} applications "
            f"(applied + updated_at < {cutoff_iso})"
        )
        return n
    except Exception as e:
        print(f"  [supabase] stale_apps run failed: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    client = supabase_client.get_client()
    n = run(client)
    print(f"stale_apps: {n} cards moved to Stale")
