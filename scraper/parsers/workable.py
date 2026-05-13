"""Workable parser.

Uses Workable's public widget endpoint:
    https://apply.workable.com/api/v3/accounts/{slug}/jobs

Each company has a slug visible in their apply.workable.com URL:
    https://apply.workable.com/walletconnect    -> slug='walletconnect'
    https://apply.workable.com/mina-foundation  -> slug='mina-foundation'

The endpoint returns JSON with shape:
    {"results": [{"title": ..., "shortcode": ..., "code": ..., "country": ...,
                  "city": ..., "remote": bool, "url": "...full_url...",
                  "description": "<html>", "telecommuting": bool, ...}],
     "total": N, ...}

We don't fetch per-job detail pages — the list response already carries
a useful description snippet, and the public apply.workable.com URL is
in the ``url`` field, so candidates can apply directly.

Add a source like:
    {"name": "WalletConnect", "url": "https://apply.workable.com/walletconnect",
     "category": "Infra"}
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "workable"

# Match slugs from apply.workable.com paths. Slugs are alphanumerics + hyphens,
# always lowercase in practice. Tolerant of trailing slash and query.
_WORKABLE_URL = re.compile(
    r"https?://apply\.workable\.com/(?P<slug>[a-z0-9][a-z0-9\-_]*)",
    re.IGNORECASE,
)

# v1 widget endpoint — public, no auth, returns full job list in one call
# (no pagination). Verified against apply.workable.com/walletconnect 2026-05-13.
# The ``details=true`` flag enrichens each row with description / locations.
_API = "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"

# Worth noting: Workable also has a paid Job Board API at
# /spi/v3/accounts/{subdomain}/jobs that returns richer fields. We use
# the public widget path because it works without an API key.


def _extract_slug(source: dict) -> str | None:
    slug = source.get("workable_slug")
    if slug:
        return str(slug).strip().lower()
    m = _WORKABLE_URL.search(source.get("url", ""))
    return m.group("slug").lower() if m else None


def can_parse(source: dict) -> bool:
    return _extract_slug(source) is not None


def _strip_html(text: str) -> str:
    """Workable's widget returns 'description' as raw HTML. Strip tags so
    the downstream classifier/scorer sees clean text. Cap at 5000 chars
    same as ashby.py."""
    if not text:
        return ""
    if text.lstrip().startswith("<"):
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:5000]


def _format_location(post: dict) -> str | None:
    """Workable list response has separate country / city fields. Combine
    them; mark remote-only roles as 'Remote' so downstream classify can
    tag remote_status correctly.
    """
    if post.get("telecommuting") and not post.get("city"):
        country = (post.get("country") or "").strip()
        return f"Remote — {country}" if country else "Remote"
    parts = []
    city = (post.get("city") or "").strip()
    country = (post.get("country") or "").strip()
    if city: parts.append(city)
    if country: parts.append(country)
    return ", ".join(parts) or None


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source)
    if not slug:
        return []

    company = (source.get("name") or slug).strip()
    category = source.get("category")
    out: list[dict] = []

    resp = session.get(
        _API.format(slug=slug),
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"Accept": "application/json"},
    )
    if resp.status_code == 404:
        # Slug not found — Workable returns 404 on unknown accounts.
        # Quiet exit so this source counts as "0 jobs found" not as a
        # consecutive failure.
        import sys
        print(f"  [workable] 404 for slug={slug} (no public board)", file=sys.stderr)
        return out
    if resp.status_code != 200:
        raise RuntimeError(f"workable API {resp.status_code} for slug={slug}")

    body = (resp.text or "").strip()
    if not body:
        return out
    try:
        payload = resp.json() or {}
    except ValueError:
        import sys
        snippet = body[:80].replace("\n", " ")
        print(f"  [workable] non-JSON for slug={slug}: {snippet!r}", file=sys.stderr)
        return out

    # Prefer the account name from Workable when available — better
    # capitalisation than the URL slug.
    account_name = (payload.get("name") or company).strip()
    jobs = payload.get("jobs") or []

    for post in jobs:
        title = (post.get("title") or "").strip()
        if not title:
            continue
        apply_url = post.get("shortlink") or post.get("url") or post.get("application_url")
        if not apply_url:
            shortcode = post.get("shortcode") or post.get("code")
            if shortcode:
                apply_url = f"https://apply.workable.com/j/{shortcode}/"
        if not apply_url:
            continue

        description = _strip_html(post.get("description") or "")
        out.append({
            "title": title,
            "company": account_name,
            "location": _format_location(post),
            "description": description or None,
            "apply_url": apply_url,
            "source_url": source["url"],
            "salary_min_usd": None,  # widget API rarely returns salary
            "salary_max_usd": None,
            "salary_source": None,
            "category": category,
        })

    return out
