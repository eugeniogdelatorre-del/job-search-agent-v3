"""Thin Supabase service-role client wrapper for scraper writes.

Fail-soft: every public function swallows exceptions and logs to stderr
rather than raising, so a Supabase outage never cascades into a failed
GitHub Actions run. Callers can detect failure via (written, errors)
return tuples or None-returns.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

UPSERT_BATCH_SIZE = 500

# Load .env once at import time so local runs work without extra wiring.
load_dotenv()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_client():
    """Return a Supabase client using the service-role key, or None if unavailable."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        print("  [supabase] SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
        return None
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("  [supabase] supabase-py not installed", file=sys.stderr)
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        print(f"  [supabase] client init failed: {e}", file=sys.stderr)
        return None


def upsert_jobs(client, rows: list[dict]) -> tuple[int, int]:
    """Upsert rows into `jobs` with on_conflict=dedup_key. Returns (written, batch_errors)."""
    if client is None or not rows:
        return (0, 0)
    written = 0
    errors = 0
    for i in range(0, len(rows), UPSERT_BATCH_SIZE):
        batch = rows[i : i + UPSERT_BATCH_SIZE]
        batch_num = i // UPSERT_BATCH_SIZE + 1
        try:
            resp = client.table("jobs").upsert(batch, on_conflict="dedup_key").execute()
            got = len(resp.data) if getattr(resp, "data", None) else len(batch)
            written += got
            print(f"  [supabase] upsert batch {batch_num}: +{got} rows")
        except Exception as e:
            errors += 1
            print(f"  [supabase] upsert batch {batch_num} FAILED: {e}", file=sys.stderr)
    return (written, errors)


def log_source_health(
    client,
    source: str,
    jobs_found: int,
    success: bool,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    if client is None:
        return
    row = {
        "source": source,
        "jobs_found": jobs_found,
        "success": success,
        "duration_ms": duration_ms,
        "error_message": (error_message or "")[:1000] or None,
        "run_at": _now_iso(),
    }
    try:
        client.table("sources_health").insert(row).execute()
    except Exception as e:
        print(f"  [supabase] sources_health insert failed for {source}: {e}", file=sys.stderr)


def fetch_scoring_config(client) -> dict:
    """Read the single-row scoring_config.config jsonb. Returns {} if unavailable or empty."""
    if client is None:
        return {}
    try:
        resp = client.table("scoring_config").select("config").eq("id", 1).single().execute()
        return getattr(resp, "data", {}).get("config") or {}
    except Exception as e:
        print(f"  [supabase] fetch scoring_config failed: {e}", file=sys.stderr)
        return {}


def mark_stale_inactive(client, inactive_after_days: int = 7) -> int:
    """Set is_active=false for jobs not seen in N days. Returns rows updated."""
    if client is None:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (inactive_after_days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    try:
        resp = (
            client.table("jobs")
            .update({"is_active": False})
            .lt("last_seen_at", cutoff_iso)
            .eq("is_active", True)
            .execute()
        )
        n = len(resp.data) if getattr(resp, "data", None) else 0
        print(f"  [supabase] marked {n} jobs inactive (last_seen_at < {cutoff_iso})")
        return n
    except Exception as e:
        print(f"  [supabase] mark_stale_inactive failed: {e}", file=sys.stderr)
        return 0


def hard_delete_old(client, delete_after_days: int = 60) -> int:
    """Delete jobs whose first_seen_at is older than N days. Returns rows deleted."""
    if client is None:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (delete_after_days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    try:
        resp = (
            client.table("jobs")
            .delete()
            .lt("first_seen_at", cutoff_iso)
            .execute()
        )
        n = len(resp.data) if getattr(resp, "data", None) else 0
        print(f"  [supabase] hard-deleted {n} jobs (first_seen_at < {cutoff_iso})")
        return n
    except Exception as e:
        print(f"  [supabase] hard_delete_old failed: {e}", file=sys.stderr)
        return 0
