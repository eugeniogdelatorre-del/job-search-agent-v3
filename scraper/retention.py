"""Retention policy: 7-day inactive marker + 60-day hard delete +
auto-stale of Applied Kanban cards untouched for 30 days.

Runs at the tail of every scrape. Idempotent — safe to run from both matrix
jobs concurrently; whichever runs second sees no work to do.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scraper import stale_apps, supabase_client
else:
    from . import stale_apps, supabase_client

INACTIVE_AFTER_DAYS = 7
DELETE_AFTER_DAYS = 60


def run(client) -> dict:
    if client is None:
        return {"inactive": 0, "deleted": 0, "staled_apps": 0}
    inactive = supabase_client.mark_stale_inactive(client, INACTIVE_AFTER_DAYS)
    deleted = supabase_client.hard_delete_old(client, DELETE_AFTER_DAYS)
    staled = stale_apps.run(client)
    return {"inactive": inactive, "deleted": deleted, "staled_apps": staled}


if __name__ == "__main__":
    client = supabase_client.get_client()
    stats = run(client)
    print(f"retention stats: {stats}")
