"""Estimate the AI cost of re-scoring the last N days under the new rules.

What "rescore" means right now:
    * geo_filter: re-run with the new "hybrid relaxed to country"
      template (scraper/geo_filter.py rules 5-8).
    * cv_score: re-run with the new skill-graph-aware prompt
      (scraper/cv_extract.py + cv_score.py _resolve_cv_payload).
    * classify: NOT re-run — classifier output is stable enough that
      re-running is rarely worth the cost. Set --include-classify to
      include it anyway.

This script ONLY estimates. It does not write to the DB and it does not
queue a workflow. Run it from a machine with the Supabase service-role
key in env (same env vars the scraper uses).

Usage:
    python -m scraper.estimate_rescore_cost                 # 7 days, geo + cv
    python -m scraper.estimate_rescore_cost --days 14
    python -m scraper.estimate_rescore_cost --include-classify

Methodology:
    1. Count jobs in scope per stage:
         - cv_score:   active + geo_filtered=true + score_total>=WARM + first_seen_at>=cutoff
         - geo_filter: active + first_seen_at>=cutoff (clears the geo flag)
         - classify:   active + first_seen_at>=cutoff
    2. Pull per-stage per-job historical cost from spend_tracking
       (mean cost_usd / jobs in that batch, from the `notes` field
       which carries jobs= count). Falls back to a hard-coded estimate
       per stage if no historical data exists yet.
    3. Multiply N * mean_cost_per_job. Print best/worst case (with /
       without prompt cache hit). Print stage cap headroom from
       STAGE_BUDGETS so the operator can decide before running.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import supabase_client
from scraper.budget import STAGE_BUDGETS, month_to_date_spend


# ---------------------------------------------------------------------------
# Fallback per-job cost estimates, used when there is no historical
# spend_tracking data to learn from. Values come from observed Haiku
# Batch pricing (see scraper/cv_score.py + classify.py + geo_filter.py
# headers) and a ~1500 token typical job description.
# ---------------------------------------------------------------------------
FALLBACK_USD_PER_JOB = {
    # classify: ~500 in, ~80 out per job × $0.50/$2.50 per MTok (Batch)
    "classify":   0.00027,
    # geo_filter: ~400 in, ~30 out per job × $0.50/$2.50 (Batch)
    "geo_filter": 0.00016,
    # cv_score: bigger — full job description as user message, system
    # prompt cached, ~700 out per job. With cache hit ratio assumed.
    "cv_score":   0.00060,
}

# Try to recover the actual jobs-per-batch from the notes field. The
# Python writers emit "jobs=N pass=... fail=..." or "jobs={n}".
_JOBS_NOTE_RE = re.compile(r"\bjobs=(\d+)\b")


def _cutoff_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ---------------------------------------------------------------------------
# Stage-scoped job counts (the size of the rescore queue)
# ---------------------------------------------------------------------------

def _count_cv_score_scope(client, cutoff_iso: str) -> int:
    """How many jobs cv_score would touch in a full rescore: active,
    geo_filtered=true, score_total >= 60, first_seen_at >= cutoff."""
    if client is None:
        return 0
    try:
        resp = (
            client.table("jobs")
            .select("id", count="exact", head=True)
            .eq("is_active", True)
            .eq("geo_filtered", True)
            .gte("score_total", 60)
            .gte("first_seen_at", cutoff_iso)
            .execute()
        )
        return int(getattr(resp, "count", 0) or 0)
    except Exception as e:
        print(f"  [estimate] count cv_score scope failed: {e}", file=sys.stderr)
        return 0


def _count_geo_filter_scope(client, cutoff_iso: str) -> int:
    """A rescore clears geo_filtered=true and re-asks the AI. Scope =
    active rows from the last N days."""
    if client is None:
        return 0
    try:
        resp = (
            client.table("jobs")
            .select("id", count="exact", head=True)
            .eq("is_active", True)
            .gte("first_seen_at", cutoff_iso)
            .execute()
        )
        return int(getattr(resp, "count", 0) or 0)
    except Exception as e:
        print(f"  [estimate] count geo_filter scope failed: {e}", file=sys.stderr)
        return 0


def _count_classify_scope(client, cutoff_iso: str) -> int:
    """Re-classify = active rows from the last N days. Same shape as
    geo_filter scope but different cost model."""
    return _count_geo_filter_scope(client, cutoff_iso)


# ---------------------------------------------------------------------------
# Historical per-job cost (learn from past spend_tracking rows)
# ---------------------------------------------------------------------------

def _mean_cost_per_job(client, operation: str, lookback_days: int = 30) -> float | None:
    """Average cost_usd / jobs across past `operation` runs in the last
    `lookback_days`. Returns None if no usable data (caller falls back
    to FALLBACK_USD_PER_JOB[operation]).
    """
    if client is None:
        return None
    cutoff = _cutoff_iso(lookback_days)
    try:
        resp = (
            client.table("spend_tracking")
            .select("cost_usd, notes")
            .eq("operation", operation)
            .gte("run_at", cutoff)
            .limit(500)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
    except Exception as e:
        print(f"  [estimate] spend history fetch failed for {operation}: {e}", file=sys.stderr)
        return None

    total_cost = 0.0
    total_jobs = 0
    for r in rows:
        cost = float(r.get("cost_usd") or 0.0)
        m = _JOBS_NOTE_RE.search(r.get("notes") or "")
        if not m:
            continue
        n = int(m.group(1))
        if n <= 0:
            continue
        total_cost += cost
        total_jobs += n

    if total_jobs == 0:
        return None
    return total_cost / total_jobs


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------

def _fmt_usd(v: float) -> str:
    if v >= 1.0:
        return f"${v:.2f}"
    if v >= 0.01:
        return f"${v:.3f}"
    return f"${v:.4f}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Estimate AI cost of rescoring the last N days under new rules.",
    )
    ap.add_argument("--days", type=int, default=7,
                    help="how many days back to rescore (default: 7)")
    ap.add_argument("--include-classify", action="store_true",
                    help="also re-run classify (rarely worth it; default off)")
    args = ap.parse_args()

    cutoff_iso = _cutoff_iso(args.days)
    print(
        f"Rescore cost estimate — last {args.days} days "
        f"(first_seen_at >= {cutoff_iso})"
    )

    sb = supabase_client.get_client()
    if sb is None:
        print("  [fatal] no supabase client (check SUPABASE_URL / SUPABASE_SERVICE_KEY)",
              file=sys.stderr)
        return 2

    # Always include geo_filter + cv_score. classify is opt-in.
    stages = ["geo_filter", "cv_score"]
    if args.include_classify:
        stages = ["classify"] + stages

    print()
    print(f"  {'Stage':<14} {'Jobs in scope':>15} {'Per-job (USD)':>17} {'Total (USD)':>15}")
    print(f"  {'-'*14} {'-'*15} {'-'*17} {'-'*15}")

    totals: dict[str, float] = {}
    grand_total = 0.0
    for stage in stages:
        if stage == "cv_score":
            n = _count_cv_score_scope(sb, cutoff_iso)
        elif stage == "geo_filter":
            n = _count_geo_filter_scope(sb, cutoff_iso)
        elif stage == "classify":
            n = _count_classify_scope(sb, cutoff_iso)
        else:
            n = 0

        per_job_hist = _mean_cost_per_job(sb, stage)
        per_job = per_job_hist if per_job_hist is not None else FALLBACK_USD_PER_JOB[stage]
        provenance = "(historical)" if per_job_hist is not None else "(fallback est.)"
        stage_total = n * per_job
        totals[stage] = stage_total
        grand_total += stage_total
        print(
            f"  {stage:<14} {n:>15,} {_fmt_usd(per_job):>17} {_fmt_usd(stage_total):>15}  {provenance}"
        )

    print()
    print(f"  Grand total estimate: {_fmt_usd(grand_total)}")

    # ── Budget headroom check ───────────────────────────────────────────
    print()
    print("Budget headroom (after rescore lands within current UTC month):")
    print(f"  {'Stage':<14} {'Rescore cost':>14} {'MTD already':>14} {'Stage cap':>12} {'After rescore':>16}")
    print(f"  {'-'*14} {'-'*14} {'-'*14} {'-'*12} {'-'*16}")
    for stage in stages:
        cap = STAGE_BUDGETS.get(stage)
        if cap is None:
            continue
        mtd_already = month_to_date_spend(sb, operation=stage)
        rescore_cost = totals[stage]
        after = mtd_already + rescore_cost
        status = "OK" if after < cap else "TRIPS CAP"
        print(
            f"  {stage:<14} {_fmt_usd(rescore_cost):>14} "
            f"{_fmt_usd(mtd_already):>14} {_fmt_usd(cap):>12} "
            f"{_fmt_usd(after):>16}  {status}"
        )

    # ── What the rescore would do ──────────────────────────────────────
    print()
    print("To actually run the rescore (NOT done by this script):")
    if args.include_classify:
        print("  1. Reset classify outputs on in-scope rows (optional):")
        print(f"     UPDATE jobs SET function_category=NULL, seniority=NULL,")
        print(f"            vertical=NULL, remote_status=NULL")
        print(f"     WHERE is_active = true AND first_seen_at >= '{cutoff_iso}';")
    print("  2. Clear geo state so geo_filter re-evaluates with the new rules:")
    print(f"     UPDATE jobs SET geo_filtered = false, geo_reject_reason = NULL")
    print(f"     WHERE first_seen_at >= '{cutoff_iso}';")
    print("  3. Delete cv_score outputs for the active resume so cv_score re-runs:")
    print(f"     DELETE FROM job_scores")
    print(f"     WHERE resume_id = (SELECT id FROM resumes WHERE is_active = true LIMIT 1)")
    print(f"       AND job_id IN (SELECT id FROM jobs WHERE first_seen_at >= '{cutoff_iso}');")
    print("  4. Manually dispatch geo_filter.yml then cv_score.yml via Actions,")
    print("     OR click 'Run Everything' (pipeline.yml) once steps 2/3 are done.")
    print()
    print("  Per-stage budget will gate the run; if any stage's headroom above")
    print("  shows TRIPS CAP, raise that stage's entry in STAGE_BUDGETS first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
