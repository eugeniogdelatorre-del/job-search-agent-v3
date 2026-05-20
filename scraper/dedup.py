"""Deterministic cross-source dedup.

`dedup_key` is the DB uniqueness constraint (schema §2). As of 2026-05-13
(audit H-3) the key includes a coarse location bucket so the same role
posted in multiple cities at one company stays as multiple distinct
rows (e.g. Coinbase "Community Manager" in SF / NYC / Remote → three
keys, three cards) instead of collapsing into one.

When two sources emit the same dedup_key within a single scrape run,
the higher `source_tier` wins (tier 3 = direct ATS > tier 2 = web3
aggregator > tier 1 = broad remote board).
"""
from __future__ import annotations

import re

# Re-exported for callers that want the raw normalizer.
__all__ = [
    "normalize_for_dedup",
    "location_bucket",
    "make_dedup_key",
    "dedup_within_run",
]


_COMPANY_SUFFIX = re.compile(r"\s*(inc|llc|ltd|gmbh|corp|co|labs|foundation)\.?$")
_NON_WORD = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize_for_dedup(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = _COMPANY_SUFFIX.sub("", s)
    s = _NON_WORD.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    return s


# A small set of explicit location buckets covering the common cases.
# Anything that doesn't match one of these falls back to the first 24
# chars of the normalized string. Buckets are intentionally COARSE so:
#   * "San Francisco, CA" and "San Francisco" map to the same bucket
#   * "Remote — Americas" and "Remote, US" map to "remote"
#   * "Buenos Aires, AR" and "BA, Argentina" map to "ar"
# while distinct buckets like "us" vs "remote" stay separate.
#
# Audit M4 (deferred — see below): "Remote, US" and "Remote, EU"
# postings still collapse onto a single ``"remote"`` bucket. The right
# fix is to encode the region into the bucket (e.g. ``"remote-us"``)
# but DOING SO IS A SHAPE-DRIFT MIGRATION — the existing rows in the
# DB carry the old bucket, and the next scrape with new logic would
# produce non-matching keys, INSERT duplicates, and re-trigger the same
# class of bug that fix_dedup_collisions.py just repaired today
# (2026-05-14). Ship it as a coordinated rollout next time: write a
# new fix_dedup_collisions-style backfill, run it on prod, then merge
# the dedup.py code change in the same window. Until then, treat
# "Remote, US" and "Remote, EU" same-(title, company) collisions as a
# known limitation — the impact is low (the deduped one keeps the
# higher source_tier, so we usually pick the better-sourced posting).
_REMOTE_HINTS = ("remote", "anywhere", "worldwide", "global")


def location_bucket(location: str | None) -> str:
    """Coarse location label used to disambiguate same-(title, company)
    postings across geographies. Returns 'any' for empty/unknown — those
    fall back to the title+company collapse.
    """
    if not location:
        return "any"
    n = location.lower().strip()
    if not n:
        return "any"
    if any(h in n for h in _REMOTE_HINTS):
        # All remote postings share one bucket — same-(title, company)
        # remote duplicates DO collapse, which is what we want today.
        # See Audit M4 deferral note above for the planned refinement.
        return "remote"
    # L7: strip state/country suffix before normalising so "City, ST"
    # and "City" produce the same bucket. Split on the first comma and
    # take only the city portion; everything after the comma is a
    # regional qualifier ("CA", "USA", "Argentina") that shouldn't
    # differentiate duplicates.
    city_part = n.split(",", 1)[0].strip() if "," in n else n
    # Strip remaining punctuation/whitespace then take the leading 24
    # chars. Enough to distinguish "San Francisco" from "New York" and
    # "Buenos Aires" from "Mexico City".
    cleaned = _WHITESPACE.sub(" ", _NON_WORD.sub(" ", city_part)).strip()
    return cleaned[:24] or "any"


def make_dedup_key(
    title: str | None,
    company: str | None,
    location: str | None = None,
) -> str:
    """Three-part dedup key: (title, company, location-bucket).

    The ``location`` arg is OPTIONAL with a None default so any caller
    that hasn't been updated still produces a stable key (just one with
    location='any', collapsing all locations like the old behavior).
    """
    return (
        f"{normalize_for_dedup(title)}|"
        f"{normalize_for_dedup(company)}|"
        f"{location_bucket(location)}"
    )


def _is_valid_key(key: str | None) -> bool:
    """Reject sentinels of empty (title, company) pairs.

    Audit M20: ``make_dedup_key("", "")`` used to return ``"|"`` which
    was truthy but semantically empty. The new 3-part key adds
    ``|any`` for missing locations, so the all-empty sentinel is now
    ``"||any"``. Both forms (and any leading-``|`` variant) are
    considered invalid so garbage rows don't collide on a single bucket.
    """
    if not key:
        return False
    # Drop the trailing |bucket part for the check; we only care about
    # whether title+company carried any signal.
    title_company = key.rsplit("|", 1)[0]
    if title_company in ("", "|"):
        return False
    return True


def _richness(job: dict) -> tuple[int, int, int]:
    """Tiebreaker tuple — higher is better.

    Primary:   source_tier (direct-company > web3 aggregator > broad board)
    Secondary: has a listed salary (proxy for "parser extracted structured data")
    Tertiary:  description length (longer = more signal for cv_score)

    Audit H2 (2026-05-20): the previous code used a strict ``>`` on
    source_tier, so the FIRST row seen on a tier tie always won, even if
    a later row had a 5000-char description and a listed salary while the
    first had neither. Using a tuple comparison ensures the richest row
    survives dedup regardless of insertion order.
    """
    has_salary = 1 if (job.get("salary_min_usd") or job.get("salary_max_usd")) else 0
    desc_len = len(job.get("description") or "")
    tier = int(job.get("source_tier") or 0)
    return (tier, has_salary, desc_len)


def dedup_within_run(jobs: list[dict]) -> list[dict]:
    """Collapse same-dedup_key jobs within a run, keeping the richest row.

    "Richest" is defined by ``_richness``: highest source_tier first,
    then listed salary, then longest description. On a full tie the first
    seen wins (stable).

    Rows with an invalid dedup_key (empty / ``"|"``) pass through
    untouched — they shouldn't share a bucket with each other or with
    well-formed rows.
    """
    best: dict[str, dict] = {}
    passthrough: list[dict] = []
    for job in jobs:
        key = job.get("dedup_key")
        if not _is_valid_key(key):
            passthrough.append(job)
            continue
        current = best.get(key)
        if current is None or _richness(job) > _richness(current):
            best[key] = job
    return list(best.values()) + passthrough
