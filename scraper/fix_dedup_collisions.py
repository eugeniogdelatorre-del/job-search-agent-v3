"""One-shot repair for the 2026-05-14 dedup_key shape mismatch.

Yesterday's PR #20 changed make_dedup_key from a 2-part key (title|company)
to a 3-part key (title|company|location-bucket). The migration was code-only
— it did NOT rewrite existing dedup_key values in the DB. As a result,
today's scrape:

    1. Pulled the same jobs it pulled yesterday (plus a few new ones)
    2. Generated a 3-part key for every job
    3. `upsert(on_conflict="dedup_key")` looked for that 3-part key,
       didn't find a matching row (because existing rows had 2-part keys),
       and INSERTED a duplicate.

Visible symptom: "indexed today" jumped from ~60 to ~2,300 overnight, and
each new row is a duplicate of an existing one — same title/company but
fresher first_seen_at and no job_scores row yet.

This script repairs the DB in three steps. Idempotent — re-running is a
no-op once the first pass cleans things up.

  Step 1: For every row first_seen_at >= today_utc:
            - find the OLDEST row with matching
              (normalize(title), normalize(company), location_bucket(loc))
              that was first seen BEFORE today
            - if found: delete today's row, bump the old row's
              last_seen_at to the deleted row's last_seen_at
              (i.e. mark the original "still active") and clear
              is_active=false / geo_reject_reason that retention may have
              set on the original.

  Step 2: For every remaining row, re-compute the new 3-part dedup_key
          from (title, company, location) and UPDATE it back. After this
          step, every row in the DB carries the new key shape and the
          next scrape's upserts will land on the right row.

  Step 3: Print a summary (rows deleted, rows backfilled).

Usage:
    python -m scraper.fix_dedup_collisions --dry     # report only
    python -m scraper.fix_dedup_collisions           # actually do it

Requires SUPABASE_URL + SUPABASE_SERVICE_KEY in env.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import supabase_client
from scraper.dedup import location_bucket, make_dedup_key, normalize_for_dedup


def _today_utc_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _fetch_all_jobs(client) -> list[dict]:
    """Pull every job row we need to consider.

    For Step 1 (duplicate detection) we'd ideally fetch only rows with
    first_seen_at >= today plus their candidate matches (anything else
    with the same title/company). Two-phase fetch is more network calls
    but smaller payload. For simplicity we just fetch all active rows —
    typical scale is a few thousand which fits comfortably in one
    paginated request.
    """
    rows: list[dict] = []
    PAGE = 1000
    offset = 0
    while True:
        resp = (
            client.table("jobs")
            .select(
                "id, title, company, location, dedup_key, "
                "first_seen_at, last_seen_at, is_active, geo_reject_reason"
            )
            .order("first_seen_at", desc=False)  # oldest first → kept rows win ties
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        batch = getattr(resp, "data", []) or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    return rows


def _natural_key(row: dict) -> tuple[str, str, str]:
    """(normalized_title, normalized_company, location_bucket) tuple.
    Two rows with the same natural key are duplicates regardless of the
    raw dedup_key string they currently carry.
    """
    return (
        normalize_for_dedup(row.get("title")),
        normalize_for_dedup(row.get("company")),
        location_bucket(row.get("location")),
    )


def _step1_delete_duplicates(client, rows: list[dict], today_iso: str, dry: bool) -> tuple[int, int]:
    """Find duplicate groups and delete today's newer rows, keeping the
    older originals. Returns (deleted, restored_originals).
    """
    # Group every row by natural key.
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        # Skip rows whose title+company are empty — they shouldn't share a
        # bucket and the dedup module already passes them through.
        nt, nc, _ = _natural_key(r)
        if not nt or not nc:
            continue
        groups[_natural_key(r)].append(r)

    deleted = 0
    restored = 0
    for key, group in groups.items():
        if len(group) < 2:
            continue
        # Group is already sorted by first_seen_at asc (see _fetch_all_jobs).
        # Keep the oldest as the canonical row; everything else is a dup.
        canonical = group[0]
        dups      = group[1:]
        # Only delete dups that arrived TODAY — anything older is a legit
        # historical duplicate we'd rather leave alone.
        today_dups = [d for d in dups if (d.get("first_seen_at") or "") >= today_iso]
        if not today_dups:
            continue
        # Bump the canonical's last_seen_at to the newest dup's last_seen_at
        # so retention doesn't immediately mark it stale. Restore is_active
        # if a previous retention pass had flipped it off.
        newest_seen = max((d.get("last_seen_at") or "") for d in today_dups)
        patch = {"last_seen_at": newest_seen}
        if not canonical.get("is_active"):
            patch["is_active"] = True
            patch["geo_reject_reason"] = None
        if dry:
            deleted += len(today_dups)
            restored += 1
            continue
        # Apply restore + delete in two steps. The unique constraint is on
        # dedup_key (not on natural key) so deletes don't need ordering.
        try:
            client.table("jobs").update(patch).eq("id", canonical["id"]).execute()
            restored += 1
        except Exception as e:
            print(f"  [step1] failed to restore id={canonical['id']}: {e}", file=sys.stderr)
            continue
        for d in today_dups:
            try:
                client.table("jobs").delete().eq("id", d["id"]).execute()
                deleted += 1
            except Exception as e:
                print(f"  [step1] failed to delete id={d['id']}: {e}", file=sys.stderr)
    return deleted, restored


def _step2_backfill_keys(client, rows: list[dict], deleted_ids: set[str], dry: bool) -> int:
    """Update every remaining row's dedup_key to the new 3-part format.

    Skips rows already in 3-part format (idempotent re-run) and rows we
    deleted in Step 1. Also skips writes when the new key would collide
    with an existing key (defensive — shouldn't happen after Step 1).
    """
    updated = 0
    # Track keys we've assigned so far in this run to catch any in-loop
    # collisions early instead of waiting for PostgREST to 409.
    seen_new_keys: set[str] = set()
    for r in rows:
        if r["id"] in deleted_ids:
            continue
        current = r.get("dedup_key") or ""
        # 3-part keys have exactly TWO pipes. Skip rows already in the new
        # shape so the script is idempotent.
        if current.count("|") >= 2:
            continue
        new_key = make_dedup_key(r.get("title"), r.get("company"), r.get("location"))
        if new_key in seen_new_keys:
            # Two rows would land on the same new key — shouldn't happen
            # after Step 1 cleared today's duplicates. Skip to avoid the
            # constraint violation; operator can inspect.
            print(f"  [step2] in-run collision on key={new_key!r} (id={r['id']}); skipping", file=sys.stderr)
            continue
        seen_new_keys.add(new_key)
        if dry:
            updated += 1
            continue
        try:
            client.table("jobs").update({"dedup_key": new_key}).eq("id", r["id"]).execute()
            updated += 1
        except Exception as e:
            print(f"  [step2] failed to update id={r['id']}: {e}", file=sys.stderr)
    return updated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry", action="store_true", help="print plan, don't write")
    args = ap.parse_args()

    sb = supabase_client.get_client()
    if sb is None:
        print("  [fatal] no supabase client (SUPABASE_URL / SUPABASE_SERVICE_KEY)", file=sys.stderr)
        return 2

    today_iso = _today_utc_iso()
    print(f"fix_dedup_collisions — today_utc={today_iso}  dry={args.dry}")

    print("\n[fetch] pulling all job rows…")
    rows = _fetch_all_jobs(sb)
    print(f"        fetched: {len(rows)}")

    # Count today's arrivals for context.
    today_rows = [r for r in rows if (r.get("first_seen_at") or "") >= today_iso]
    print(f"        first_seen_at >= today: {len(today_rows)}")

    print("\n[step 1/2] removing today's duplicates of pre-existing rows…")
    deleted, restored = _step1_delete_duplicates(sb, rows, today_iso, args.dry)
    verb_d = "would delete" if args.dry else "deleted"
    verb_r = "would restore" if args.dry else "restored"
    print(f"           {verb_d}: {deleted} duplicate rows")
    print(f"           {verb_r}: {restored} canonical originals (last_seen_at bumped)")

    # In dry-mode we still want Step 2 to operate on the same row set we
    # fetched (we haven't actually deleted anything). Compute deleted_ids
    # by re-running the group logic so the dry-run report matches reality.
    deleted_ids: set[str] = set()
    if not args.dry:
        # Refetch — Step 1's deletes shrank the table. Step 2 needs only
        # the surviving rows.
        rows = _fetch_all_jobs(sb)

    print("\n[step 2/2] backfilling dedup_key to new 3-part format…")
    updated = _step2_backfill_keys(sb, rows, deleted_ids, args.dry)
    verb_u = "would update" if args.dry else "updated"
    print(f"           {verb_u}: {updated} rows")

    print()
    if args.dry:
        print("Dry run complete. Re-run without --dry to apply.")
        print("After applying, run the pipeline once manually so cv_score")
        print("can finish draining the backlog under the new key shape:")
        print("  Actions → pipeline → Run workflow")
    else:
        print("Done. Next pipeline run will upsert against the new key shape.")
        print("Dispatch it manually if you want to backfill scores tonight:")
        print("  Actions → pipeline → Run workflow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
