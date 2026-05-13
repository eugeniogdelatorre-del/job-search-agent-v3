"""Scrape orchestrator — Phase 2.

Pipeline:
    1. Load v3 group sources from sources.json (X feeds filtered at load time).
       Suspended sources (5+ consecutive failures) are fetched from Supabase
       and skipped; a skip log is emitted so they appear in sources_health.
    2. For each source: pick a parser (first matching in priority list),
       scrape, log sources_health with timing + outcome, update source_states.
    3. Compute dedup_key + source_tier on each raw job.
       Jobs from CJL boost companies are upgraded to tier 3 (direct company).
    4. Junk filter + aggregator title unmasher (junk_filters.clean_jobs)
    5. Dedup within this run (keep highest tier on collision)
    6. Score every surviving job with the rule-based 6-dim scorer.
       Config is hard-coded in score.DEFAULT_CONFIG (no DB merge — /tune removed).
    7. Upsert into `jobs` with on_conflict=dedup_key
    8. Run retention (7-day inactive, 60-day delete)

Parser priority (first match wins): greenhouse > lever > ashby > workday >
bamboohr > teamtailor > cryptojobslist > web3career > weworkremotely > generic (BS4 fallback).

Usage:
    python scraper/scrape.py                        # all sources (daily run)
    python scraper/scrape.py --group 1              # group 1 only (debug)
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
    bamboohr,
    cryptojobslist,
    generic,
    getonbrd,
    greenhouse,
    lever,
    teamtailor,
    web3career,
    weworkremotely,
    workable,
    workday,
)
from scraper.parsers.base import make_session
from scraper.score import DEFAULT_CONFIG, score_job

# Parser registry — ordered. First `can_parse(source)` match wins.
# workable comes before generic so apply.workable.com URLs aren't sent
# through the generic HTML-fallback path. It needs to be after the more
# specific ATS parsers (none of which match Workable URLs).
PARSERS = [
    greenhouse,
    lever,
    ashby,
    workday,
    bamboohr,
    teamtailor,
    workable,
    cryptojobslist,
    web3career,
    weworkremotely,
    getonbrd,  # LATAM aggregator — pulls 500+ jobs per run
    generic,
]

DELAY_BETWEEN_REQUESTS_SECONDS = 1
# Audit L1: SUSPENSION_THRESHOLD removed — the live value is
# SUSPEND_AFTER_CONSECUTIVE_FAILURES in supabase_client.py (=7). The
# unused 5 here was misleading anyone reading scrape.py expecting it to
# be the source of truth.

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


def _normalize_company(name: str) -> str:
    return name.lower().strip()


def _enrich(job: dict, source: dict, cjl_boost: set[str]) -> dict:
    """Attach dedup_key, source_tier, source, source_url, last_seen_at."""
    now_iso = datetime.now(timezone.utc).isoformat()
    tier = _infer_tier(source)

    # Upgrade tier for jobs whose company appears in the CJL boost list.
    # This ensures formerly-individual-page companies discovered via the
    # JSON feed are treated as direct-company hits (tier 3) rather than
    # board hits (tier 1/2).
    if cjl_boost and job.get("_cjl_company"):
        if _normalize_company(job["_cjl_company"]) in cjl_boost:
            tier = 3

    return {
        **job,
        "dedup_key": make_dedup_key(
            job.get("title"), job.get("company"), job.get("location")
        ),
        "source": source.get("name") or "unknown",
        "source_tier": tier,
        "source_url": job.get("source_url") or source.get("url"),
        "last_seen_at": now_iso,
        "is_active": True,
    }


def _scrape_source(
    session: requests.Session,
    source: dict,
    client,
    cjl_boost: set[str],
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
        supabase_client.update_source_state(client, company, success=True)
        print(f"  [skip] {company}: no parser matched")
        return []

    print(f"  [{parser.name}] {company}")
    start = time.time()
    jobs: list[dict] = []
    success = False
    error_message: str | None = None
    try:
        raw = parser.parse(session, source)
        jobs = [_enrich(j, source, cjl_boost) for j in raw]
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
    supabase_client.update_source_state(client, company, success=success)
    return jobs


def _job_to_row(job: dict, score: int, breakdown: dict) -> dict:
    """Transform an enriched raw job into a Supabase `jobs` row payload."""
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
    ap.add_argument("--group", type=int, required=False, default=None, choices=[1, 2],
                    help="v3 source group (1 or 2); omit to run all sources")
    ap.add_argument("--dry", action="store_true", help="don't write to Supabase")
    ap.add_argument("--limit", type=int, default=None, help="debug: only first N sources")
    ap.add_argument("--no-retention", action="store_true", help="skip the retention pass")
    args = ap.parse_args()

    print(f"scrape v3 — group={args.group if args.group is not None else 'all'}  dry={args.dry}  started={datetime.now(timezone.utc).isoformat()}")

    client = None if args.dry else supabase_client.get_client()
    if args.dry:
        print("  [dry] skipping Supabase writes")
    elif client is None:
        print("  [fatal] no Supabase client — set SUPABASE_URL + SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    # Load CJL boost company names (normalised to lowercase for comparison).
    data = sources.load_sources_file()
    cjl_boost: set[str] = {
        _normalize_company(c)
        for c in (data.get("metadata", {}).get("cjl_boost_companies") or [])
    }
    if cjl_boost:
        print(f"  CJL boost list: {len(cjl_boost)} companies")

    # Fetch suspended sources so we can skip them.
    suspended: set[str] = supabase_client.fetch_suspended_sources(client)
    if suspended:
        print(f"  suspended sources ({len(suspended)}): {sorted(suspended)}")

    all_sources = (
        sources.get_all_sources()
        if args.group is None
        else sources.get_sources_for_group(args.group)
    )
    if args.limit:
        all_sources = all_sources[: args.limit]
    group_label = f"group {args.group}" if args.group is not None else "all groups"
    print(f"  {len(all_sources)} sources loaded ({group_label})")

    config = DEFAULT_CONFIG
    print(f"  scoring thresholds: {config['thresholds']}")

    session = make_session()
    all_jobs: list[dict] = []
    for src in all_sources:
        company = src.get("name") or "unknown"
        if company in suspended:
            print(f"  [suspended] {company}: skipping — re-enable in /settings")
            supabase_client.log_source_health(
                client,
                source=company,
                jobs_found=0,
                success=False,
                duration_ms=0,
                error_message="suspended",
            )
            continue
        all_jobs.extend(_scrape_source(session, src, client, cjl_boost))
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
