"""Parser protocol for source-specific scrapers.

Each parser owns a narrow domain (Greenhouse boards, Lever postings, etc.)
and returns normalized raw-job dicts. The scrape orchestrator picks a parser
per source via `can_parse(source)` and falls back to skipping when no parser
matches (Phase 1). Phase 2 adds more parsers + a generic HTML fallback.

Raw job shape (what each parser returns):
    {
      "title":        str,
      "company":      str,
      "location":     str | None,
      "description":  str | None,
      "apply_url":    str,
      "source_url":   str,
      "salary_min_usd": int | None,
      "salary_max_usd": int | None,
      "salary_source":  str | None,   # "listed" when parser extracted from structured data
      "category":     str | None,     # passes through the v2 category
    }

Downstream (score.py, supabase_client.job_to_row) enriches with:
    source, source_tier, dedup_key, score_total, score_breakdown, first_seen_at,
    last_seen_at, is_active.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import requests


@runtime_checkable
class Parser(Protocol):
    name: str

    def can_parse(self, source: dict) -> bool: ...

    def parse(self, session: requests.Session, source: dict) -> list[dict]: ...


REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    })
    return s
