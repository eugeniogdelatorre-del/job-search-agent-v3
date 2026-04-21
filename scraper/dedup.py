"""Deterministic cross-source dedup.

`dedup_key` is the DB uniqueness constraint (schema §2). Computed as
`normalize(title)|normalize(company)` so the same posting reached via
multiple sources collapses to one row.

When two sources emit the same dedup_key within a single scrape run,
the higher `source_tier` wins (tier 3 = direct ATS > tier 2 = web3
aggregator > tier 1 = broad remote board).
"""
from __future__ import annotations

import re

# Re-exported for callers that want the raw normalizer.
__all__ = ["normalize_for_dedup", "make_dedup_key", "dedup_within_run"]


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


def make_dedup_key(title: str | None, company: str | None) -> str:
    return f"{normalize_for_dedup(title)}|{normalize_for_dedup(company)}"


def dedup_within_run(jobs: list[dict]) -> list[dict]:
    """Collapse same-dedup_key jobs within a run, keeping highest source_tier.

    Ties on source_tier keep the first seen (stable).
    """
    best: dict[str, dict] = {}
    for job in jobs:
        key = job.get("dedup_key")
        if not key:
            continue
        current = best.get(key)
        if current is None:
            best[key] = job
            continue
        if (job.get("source_tier") or 0) > (current.get("source_tier") or 0):
            best[key] = job
    return list(best.values())
