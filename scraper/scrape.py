"""Scrape orchestrator — Phase 2.

Pipeline:
    1. Load v3 group sources from sources.json (X feeds filtered at load time)
    2. For each source: pick a parser (first matching in priority list),
       scrape, log sources_health with timing + outcome
    3. Compute dedup_key + source_tier on each raw job
    4. Junk filter + aggregator title unmasher (junk_filters.clean_jobs)
    5. Dedup within this run (keep highest tier on collision)
    6. Score every surviving job with the rule-based 6-dim scorer,
       reading scoring_config from Supabase (merged over DEFAULT_CONFIG)
    7. Upsert into `jobs` with on_conflict=dedup_key
    8. Run retention (7-day inactive, 60-day delete)

Parser priority (first match wins): greenhouse > lever > ashby > workday >
cryptojobslist > web3career > weworkremotely > generic (BS4 fallback).

Usage:
    python scraper/scrape.py --group 1
    python scraper/scrape.py --group 2
    python scraper/scrape.py --group 1 --dry        # no DB writes
    python scraper/scrape.py --group 1 --limit 3    # debug: only first 3 sources
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Support both `python scraper/scrape.py --group 1` and `python -m scraper.scrape --group 1`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from scraper import junk_filters, retention, sources, supabase_client
from scraper.dedup import dedup_within_run, make_dedup_key
from scraper.parsers import (
    ashby,
    cryptojobslist,
    generic,
    greenhouse,
    lever,
    web3career,
    weworkremotely,
    workday,
)
from scraper.parsers.base import make_session
from scraper.score import resolve_config, score_job

# Parser registry — ordered. First `can_parse(source)` match wins.
# Dedicated ATS/aggregator parsers before the generic BS4 fallback.
PARSERS = [
    greenhouse,
    lever,
    ashby,
    workday,
    cryptojobslist,
    web3career,
    weworkremotely,
    generic,
]

DELAY_BETWEEN_REQUESTS_SECONDS = 1

# v2 source tier inference (mirrors jobs_cleanup.infer_source_tier).
WEB3_AGGREGATOR_NAMES = {"cryptojobslist", "web3.career", "cryptocurrencyjobs"}
BROAD_BOARD_CATEGORIES = {"Remote_Board", "Board"}


def _pick_parser(source: dict):
    for p in PARSERS:
        if p.can_parse(source):
            return p
    return None


def _infer_tier(source: dict) -> int:
    company_lower = (source.get("name") or "").lower()
    if company_lower in WEB3_AGGREGATOR_NAMES:
        return 2
    if source.get("category") in BROAD_BOARD_CATEGORIES:
        return 1
    return 3  # direct company / ATS


def _enrich(job: dict, source: dict) -> dict:
    """Attach dedup_key, source_tier, source, source_url, last_seen_at to raw parser output."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        **job,
        "dedup_key": make_dedup_key(job.get("title"), job.get("company")),
        "source": source.get("name") or "unknown",
        "source_tier": _infer_tier(source),
        "source_url": job.get("source_url") or source.get("url"),
        "last_seen_at": now_iso,
        "is_active": True,
    }


def _scrape_source(
    session: requests.Session,
    source: dict,
    client,
) -> list[dict]:
    company = source.get("name") or "unknown"
    parser = _pick_parser(source)
    if parser is None:
        supabase_client.log_source_health(
            client,
            source=company,
            jobs_found=0,
            success=True,
            duration_ms=0,
            error_message="no_parser_matched",
        )
        print(f"  [skip] {company}: no parser matched")
        return []

    print(f"  [{parser.name}] {company}")
    start = time.time()
    jobs: list[dict] = []
    success = False
    error_message: str | None = None
    try:
        raw = parser.parse(session, source)
        jobs = [_enrich(j, source) for j in raw]
        success = True
    except Exception as e:
        error_message = str(e)[:500]
        print(f"  [ERR] {company}: {e}", file=sys.stderr)

    duration_ms = int((time.time() - start) * 1000)
    supabase_client.log_source_health(
        client,
        source=company,
        jobs_found=len(jobs),
        success=success,
        duration_ms=duration_ms,
        error_message=error_message,
    )
    return jobs


def _job_to_row(job: dict, score: int, breakdown: dict) -> dict:
    """Transform an enriched raw job into a Supabase `jobs` row payload.

    Fields intentionally omitted from the payload are preserved on upsert:
      - first_seen_at (DB default on insert; preserved on conflict)
      - function_category, function_confidence, seniority, vertical, remote_status
        (these get filled by the AI classifier in Phase 3 — don't clobber)
    """
    return {
        "dedup_key": job["dedup_key"],
        "title": (job.get("title") or "").strip()[:500],
        "company": (job.get("company") or "").strip()[:200] or None,
        "location": (job.get("location") or "")[:200] or None,
        "description": (job.get("description") or "")[:5000] or None,
        "apply_url": (job.get("apply_url") or "")[:1000] or None,
        "source": job["source"][:100],
        "source_tier": job["source_tier"],
        "source_url": (job.get("source_url") or "")[:1000] or None,
        "salary_min_usd": job.get("salary_min_usd"),
        "salary_max_usd": job.get("salary_max_usd"),
        "salary_source": job.get("salary_source"),
        "score_total": score,
        "score_breakdown": breakdown,
        "last_seen_at": job["last_seen_at"],
        "is_active": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Job scrape orchestrator — v3")
    ap.add_argument("--group", type=int, required=True, choices=[1, 2], help="v3 super-group")
    ap.add_argument("--dry", action="store_true", help="don't write to Supabase")
    ap.add_argument("--limit", type=int, default=None, help="debug: only first N sources")
    ap.add_argument("--no-retention", action="store_true", help="skip the retention pass")
    args = ap.parse_args()

    print(f"scrape v3 — group={args.group}  dry={args.dry}  started={datetime.now(timezone.utc).isoformat()}")

    client = None if args.dry else supabase_client.get_client()
    if args.dry:
        print("  [dry] skipping Supabase writes")
    elif client is None:
        print("  [fatal] no Supabase client — set SUPABASE_URL + SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    group_sources = sources.get_sources_for_group(args.group)
    if args.limit:
        group_sources = group_sources[: args.limit]
    print(f"  {len(group_sources)} sources loaded for group {args.group}")

    config = resolve_config(supabase_client.fetch_scoring_config(client) if client else {})
    print(f"  scoring thresholds: {config['thresholds']}")

    session = make_session()
    all_jobs: list[dict] = []
    for src in group_sources:
        all_jobs.extend(_scrape_source(session, src, client))
        time.sleep(DELAY_BETWEEN_REQUESTS_SECONDS)

    print(f"\nraw jobs: {len(all_jobs)}")

    cleaned, cleanup_stats = junk_filters.clean_jobs(all_jobs)
    print(
        f"after cleanup: {len(cleaned)}  "
        f"(junk dropped={cleanup_stats['junk_dropped']}, unmashed={cleanup_stats['unmashed']})"
    )

    deduped = dedup_within_run(cleaned)
    print(f"after dedup within run: {len(deduped)}")

    rows: list[dict] = []
    gate_counts: dict[str, int] = {}
    for job in deduped:
        total, breakdown = score_job(job, config)
        if breakdown.get("gate_failed"):
            gate_counts[breakdown["gate_failed"]] = gate_counts.get(breakdown["gate_failed"], 0) + 1
        rows.append(_job_to_row(job, total, breakdown))

    if gate_counts:
        print(f"  gate rejects: {sum(gate_counts.values())} -> {dict(list(gate_counts.items())[:10])}")

    if args.dry:
        print(f"[dry] would upsert {len(rows)} rows. Example row:")
        if rows:
            sample = {k: rows[0].get(k) for k in ("dedup_key", "title", "company", "score_total", "source_tier")}
            print(f"        {sample}")
        return 0

    written, errors = supabase_client.upsert_jobs(client, rows)
    print(f"\nupsert: {written}/{len(rows)} rows written, {errors} batch errors")

    if not args.no_retention:
        stats = retention.run(client)
        print(f"retention: {stats}")

    print(f"done: {datetime.now(timezone.utc).isoformat()}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
