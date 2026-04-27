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


# 30 s avoids false-failure on JS-heavy / slow endpoints like Fuel Network.
REQUEST_TIMEOUT_SECONDS = 30

# Realistic Chrome 124 UA string — required to pass Cloudflare's bot check on
# several crypto-native sites that inspect both UA and sec-ch-ua.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        # Language / encoding
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Encoding": "gzip, deflate, br",
        # Client-hints — needed to pass Cloudflare's sec-ch-ua check
        "sec-ch-ua": _SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        # Fetch metadata — mimic a top-level navigation
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def make_api_session() -> requests.Session:
    """Lightweight session for JSON API calls (ATS backends, JSON feeds).

    Sends a minimal Accept header suitable for API endpoints rather than the
    full browser navigation headers used by make_session().
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": _SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    })
    return s
