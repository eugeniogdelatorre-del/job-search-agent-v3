"""Retroactively apply the new scoring rules to recent job rows.

When the scoring concepts change — new role keywords, lowered warm
threshold, salary band penalty, looser geo rules — existing rows in the
DB still carry the OLD ``score_total`` / ``score_breakdown`` /
``geo_filtered`` values from their original scrape. The cron pipeline
processes only NEW arrivals, so the backlog never sees the new logic.

This script touches three things to fix that:

  1. ``UPDATE jobs SET score_total, score_breakdown = <new>``
     Re-runs ``score.py::score_job`` against each in-scope row so the
     rule-score reflects new keywords / penalties / salary band.

  2. ``UPDATE jobs SET geo_filtered = false, geo_reject_reason = NULL,
                       is_active = true``
     For rows previously rejected by geo_filter. The next geo_filter.yml
     run will re-evaluate them under the new rules (hybrid-in-country,
     remote-LATAM-friendly hybrid).

  3. ``DELETE FROM job_scores WHERE resume_id = <active> AND job_id IN
     (in-scope ids)``
     Removes existing AI scores so cv_score re-evaluates with the new
     prompt / skill graph / WARM_THRESHOLD.

After this script runs, dispatch the pipeline (or `geo_filter.yml`
manually) and the new concepts will be applied to the last N days.

Usage:
    python -m scraper.rescore_recent              # default 14 days
    python -m scraper.rescore_recent --days 30
    python -m scraper.rescore_recent --dry        # print what would change

The script is IDEMPOTENT — running twice with the same --days produces
the same end state. It is also additive: the operator can rerun after
each scoring-concept change without manual cleanup.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import supabase_client
from scraper.score import DEFAULT_CONFIG, score_job


def _fetch_in_scope_jobs(client, cutoff_iso: str) -> list[dict]:
    """All rows with first_seen_at >= cutoff. Selects only the fields
    ``score_job`` needs plus id so we can write back. Paginates because
    Supabase's default cap is 1000.
    """
    rows: list[dict] = []
    PAGE = 500
    offset = 0
    while True:
        resp = (
            client.table("jobs")
            .select(
                "id, title, company, location, description, "
                "salary_min_usd, salary_max_usd, source_tier"
            )
            .gte("first_seen_at", cutoff_iso)
            .order("first_seen_at", desc=True)
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


def _recompute_rule_scores(client, rows: list[dict], dry: bool) -> int:
    """Score each row under the CURRENT score.py rules and patch
    score_total + score_breakdown back. Returns rows updated.
    """
    written = 0
    for row in rows:
        total, breakdown = score_job(row, DEFAULT_CONFIG)
        patch = {"score_total": total, "score_breakdown": breakdown}
        if dry:
            written += 1
            continue
        try:
            resp = (
                client.table("jobs")
                .update(patch)
                .eq("id", row["id"])
                .execute()
            )
            if getattr(resp, "data", None):
                written += 1
        except Exception as e:
            print(f"  [rescore] update id={row['id']} failed: {e}", file=sys.stderr)
    return written


def _reset_geo_state(client, cutoff_iso: str, dry: bool) -> int:
    """Re-enable + un-flag rows that were rejected by the OLD geo rules,
    so geo_filter re-evaluates them. Only touches rows that were
    previously geo-rejected (``geo_reject_reason IS NOT NULL``) — rows
    that passed geo before stay as-is.
    """
    if dry:
        # Approximate count for the dry-run report.
        resp = (
            client.table("jobs")
            .select("id", count="exact", head=True)
            .gte("first_seen_at", cutoff_iso)
            .not_.is_("geo_reject_reason", "null")
            .execute()
        )
        return int(getattr(resp, "count", 0) or 0)
    try:
        resp = (
            client.table("jobs")
            .update(
                {
                    "geo_filtered": False,
                    "geo_reject_reason": None,
                    "is_active": True,
                },
                count="exact",
            )
            .gte("first_seen_at", cutoff_iso)
            .not_.is_("geo_reject_reason", "null")
            .execute()
        )
        return int(getattr(resp, "count", 0) or 0)
    except Exception as e:
        print(f"  [rescore] geo reset failed: {e}", file=sys.stderr)
        return 0


def _active_resume_id(client) -> str | None:
    resp = (
        client.table("resumes")
        .select("id")
        .eq("is_active", True)
        .order("id")
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return str(rows[0]["id"]) if rows else None


def _clear_cv_scores(client, cutoff_iso: str, resume_id: str, dry: bool) -> int:
    """Delete job_scores rows for the active resume + in-scope jobs.
    The next cv_score run will re-evaluate them with the new prompt /
    skill graph / warm threshold.
    """
    # Two-step: collect in-scope job ids, then delete by (resume_id, job_id).
    job_ids: list[str] = []
    PAGE = 500
    offset = 0
    while True:
        resp = (
            client.table("jobs")
            .select("id")
            .gte("first_seen_at", cutoff_iso)
            .range(offset, offset + PAGE - 1)
            .execute()
        )
        batch = getattr(resp, "data", []) or []
        if not batch:
            break
        job_ids.extend(str(r["id"]) for r in batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    if not job_ids:
        return 0
    if dry:
        # Approximate: count job_scores rows for this resume + in-scope jobs.
        # Single query with .in_() works up to ~200 ids without URL overflow.
        # For >200 we chunk.
        total = 0
        for i in range(0, len(job_ids), 100):
            chunk = job_ids[i : i + 100]
            resp = (
                client.table("job_scores")
                .select("job_id", count="exact", head=True)
                .eq("resume_id", resume_id)
                .in_("job_id", chunk)
                .execute()
            )
            total += int(getattr(resp, "count", 0) or 0)
        return total
    deleted = 0
    for i in range(0, len(job_ids), 100):
        chunk = job_ids[i : i + 100]
        try:
            resp = (
                client.table("job_scores")
                .delete(count="exact")
                .eq("resume_id", resume_id)
                .in_("job_id", chunk)
                .execute()
            )
            deleted += int(getattr(resp, "count", 0) or 0)
        except Exception as e:
            print(f"  [rescore] job_scores delete chunk {i} failed: {e}", file=sys.stderr)
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rescore the last N days under the current scoring rules.",
    )
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry", action="store_true", help="print counts, don't write")
    ap.add_argument(
        "--skip-rule-rescore",
        action="store_true",
        help="don't recompute score_total / score_breakdown (faster, but new keywords won't unlock previously-cold jobs)",
    )
    ap.add_argument(
        "--skip-geo-reset",
        action="store_true",
        help="don't reset geo_filtered on previously-rejected jobs",
    )
    ap.add_argument(
        "--skip-cv-clear",
        action="store_true",
        help="don't delete job_scores rows (cv_score won't re-evaluate)",
    )
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_iso = cutoff.isoformat()
    print(f"rescore_recent — days={args.days}  cutoff={cutoff_iso}  dry={args.dry}")

    sb = supabase_client.get_client()
    if sb is None:
        print("  [fatal] no supabase client (SUPABASE_URL / SUPABASE_SERVICE_KEY)", file=sys.stderr)
        return 2

    # ── 1. Rule re-score ────────────────────────────────────────────────
    if not args.skip_rule_rescore:
        print("\n[1/3] Recomputing rule-score on in-scope rows…")
        rows = _fetch_in_scope_jobs(sb, cutoff_iso)
        print(f"      in-scope rows: {len(rows)}")
        updated = _recompute_rule_scores(sb, rows, args.dry)
        verb = "would update" if args.dry else "updated"
        print(f"      {verb}: {updated}")
    else:
        print("\n[1/3] SKIPPED rule re-score (--skip-rule-rescore)")

    # ── 2. Geo state reset ─────────────────────────────────────────────
    if not args.skip_geo_reset:
        print("\n[2/3] Resetting geo state on previously-rejected rows…")
        n = _reset_geo_state(sb, cutoff_iso, args.dry)
        verb = "would re-enable" if args.dry else "re-enabled"
        print(f"      {verb}: {n}")
    else:
        print("\n[2/3] SKIPPED geo reset (--skip-geo-reset)")

    # ── 3. Clear cv_score for active CV ────────────────────────────────
    if not args.skip_cv_clear:
        print("\n[3/3] Clearing existing job_scores for active CV…")
        rid = _active_resume_id(sb)
        if not rid:
            print("      no active resume — nothing to clear")
        else:
            n = _clear_cv_scores(sb, cutoff_iso, rid, args.dry)
            verb = "would delete" if args.dry else "deleted"
            print(f"      resume={rid}  {verb}: {n}")
    else:
        print("\n[3/3] SKIPPED cv_score clear (--skip-cv-clear)")

    print()
    if args.dry:
        print("Dry run complete. Re-run without --dry to apply.")
    else:
        print("Done. Next steps:")
        print("  1. Dispatch geo_filter.yml manually (Actions → geo_filter → Run workflow).")
        print("     When it completes, workflow_run will chain into cv_score.yml.")
        print("  2. Or click the 'Run Pipeline' button in the dashboard — it'll")
        print("     scrape first (no-op for already-scraped jobs), then re-run")
        print("     classify / geo_filter / cv_score in sequence.")
        print("  3. cv_score will auto-detect the backlog (job_scores empty for")
        print("     the active CV) and bump its per-run limit to "
              "MAX_JOBS_BACKLOG_DRAIN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
