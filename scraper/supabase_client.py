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


def get_pipeline_owner_user_id() -> str | None:
    """The single user whose active resume the scraper services.

    Audit C2 (2026-05-19): cv_score / geo_filter / weekly_summary all
    used to do an unscoped ``.eq("is_active", True).limit(1)`` lookup,
    which silently picked whichever ``resumes`` row had the lowest id
    across all users. With the auth allowlist now widened past one
    person, that meant the next user to activate a CV could quietly
    redirect the daily AI spend onto their resume.

    Set ``PIPELINE_OWNER_USER_ID`` in GitHub Actions secrets to the
    Supabase ``auth.users.id`` of the owner. The pipeline refuses to
    run if it's unset (fail-closed) rather than silently scoring
    against an arbitrary user's CV.

    Empty string is treated as unset — GitHub Actions sometimes
    surfaces a missing secret as "" instead of unset, and we want both
    paths to trip the refuse-to-run guard.
    """
    val = os.environ.get("PIPELINE_OWNER_USER_ID")
    return val if val else None


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


def fetch_suspended_sources(client) -> set[str]:
    """Return a set of source names that are currently suspended.

    Returns an empty set on any error so a Supabase outage never
    blocks the scrape run.
    """
    if client is None:
        return set()
    try:
        resp = (
            client.table("source_states")
            .select("source_name")
            .eq("suspended", True)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        return {r["source_name"] for r in rows}
    except Exception as e:
        print(f"  [supabase] fetch_suspended_sources failed: {e}", file=sys.stderr)
        return set()


# Suspend a source after 7 consecutive failed daily scrapes (= 1 full week).
# Was 5; bumped to 7 so a week-long upstream outage doesn't suspend an
# otherwise healthy source.
SUSPEND_AFTER_CONSECUTIVE_FAILURES = 7


def update_source_state(client, source_name: str, success: bool) -> None:
    """Increment or reset consecutive_failures for a source.

    On the 7th consecutive failure the source is marked suspended=true.
    On any success the counter resets and suspended is cleared.

    Audit N-H2: now calls the ``bump_source_state`` Postgres function
    (deployed via ``scraper/sql/001_source_states_rpc.sql``) so the
    increment is atomic under a Postgres advisory + row lock. Falls back
    to the previous read-modify-write path if the RPC isn't deployed
    yet — that path is racy but preserves ``suspended_at`` correctly
    (audit H19), so worst-case symptom is an under-count of
    ``consecutive_failures`` during concurrent failures of the same
    source. The fallback emits a one-time-per-process warning so the
    operator knows to deploy the migration.
    """
    if client is None:
        return
    try:
        client.rpc(
            "bump_source_state",
            {
                "p_source_name": source_name,
                "p_success": success,
                "p_suspend_threshold": SUSPEND_AFTER_CONSECUTIVE_FAILURES,
            },
        ).execute()
        return
    except Exception as e:
        # PostgREST returns code PGRST202 / 42883 when the function isn't
        # found. Anything else (e.g. permission denied, transient network)
        # is genuine and worth surfacing. We warn-once on missing-function
        # then fall through to the legacy path; for other errors we log
        # AND continue to the fallback so a Supabase hiccup mid-scrape
        # doesn't lose the bookkeeping.
        msg = str(e)
        if "PGRST202" in msg or "42883" in msg or "function" in msg.lower() and "does not exist" in msg.lower():
            _warn_once_rpc_missing()
        else:
            print(
                f"  [supabase] bump_source_state rpc failed for "
                f"{source_name} ({type(e).__name__}: {e}); falling back to "
                "read-modify-write",
                file=sys.stderr,
            )
    _update_source_state_legacy(client, source_name, success)


_RPC_MISSING_WARNED = False


def _warn_once_rpc_missing() -> None:
    global _RPC_MISSING_WARNED
    if _RPC_MISSING_WARNED:
        return
    _RPC_MISSING_WARNED = True
    print(
        "  [supabase] bump_source_state RPC not found in DB. Deploy "
        "scraper/sql/001_source_states_rpc.sql via Supabase Studio to "
        "eliminate the consecutive_failures race. Falling back to "
        "read-modify-write for now.",
        file=sys.stderr,
    )


def _update_source_state_legacy(client, source_name: str, success: bool) -> None:
    """Pre-RPC implementation kept as fallback. Documented at the call
    site. Preserves the H19 fix (suspended_at preservation) but is racy
    on concurrent failures of the same source.
    """
    now = _now_iso()
    try:
        resp = (
            client.table("source_states")
            .select("consecutive_failures, suspended, suspended_at")
            .eq("source_name", source_name)
            .maybe_single()
            .execute()
        )
        current = getattr(resp, "data", None) or {}
        failures = current.get("consecutive_failures", 0)
        was_suspended = bool(current.get("suspended"))

        if success:
            row = {
                "source_name": source_name,
                "consecutive_failures": 0,
                "suspended": False,
                "suspended_at": None,
                "last_success_at": now,
                "updated_at": now,
            }
        else:
            new_failures = failures + 1
            newly_suspended = (
                new_failures >= SUSPEND_AFTER_CONSECUTIVE_FAILURES
                and not was_suspended
            )
            row = {
                "source_name": source_name,
                "consecutive_failures": new_failures,
                "suspended": was_suspended or newly_suspended,
                "updated_at": now,
            }
            if newly_suspended:
                row["suspended_at"] = now
                print(
                    f"  [supabase] source '{source_name}' suspended after "
                    f"{new_failures} consecutive failures"
                )

        client.table("source_states").upsert(row, on_conflict="source_name").execute()
    except Exception as e:
        print(f"  [supabase] update_source_state failed for {source_name}: {e}", file=sys.stderr)


def _affected_count(resp, fallback: int = 0) -> int:
    """Read the affected-row count off a PostgREST response.

    ``count="exact"`` on ``update``/``delete`` sets ``resp.count`` to the
    number of rows the server actually changed. We prefer that over
    ``len(resp.data)`` because some Postgres/PostgREST configurations
    return an empty representation array even when rows were modified
    (audit H18). Falls back to ``len(resp.data)`` if ``count`` is None.
    """
    n = getattr(resp, "count", None)
    if n is not None:
        return int(n)
    data = getattr(resp, "data", None) or []
    return len(data) if data else fallback


def mark_stale_inactive(client, inactive_after_days: int = 7) -> int:
    """Set is_active=false for jobs not seen in N days. Returns rows updated."""
    if client is None:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (inactive_after_days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    try:
        resp = (
            client.table("jobs")
            .update({"is_active": False}, count="exact")
            .lt("last_seen_at", cutoff_iso)
            .eq("is_active", True)
            .execute()
        )
        n = _affected_count(resp)
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
            .delete(count="exact")
            .lt("first_seen_at", cutoff_iso)
            .execute()
        )
        n = _affected_count(resp)
        print(f"  [supabase] hard-deleted {n} jobs (first_seen_at < {cutoff_iso})")
        return n
    except Exception as e:
        print(f"  [supabase] hard_delete_old failed: {e}", file=sys.stderr)
        return 0
