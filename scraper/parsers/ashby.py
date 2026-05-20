"""Ashby HQ parser.

Uses the public Job Board API:
    https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true

Slug resolution (first match wins):
    1. source dict has an "ashby_slug" key  → use it directly.
       This lets VC portfolio boards and companies that host their Ashby board
       on a custom domain (jobs.paradigm.xyz, jobs.dragonfly.xyz, …) bypass
       URL parsing while still hitting the JSON API.
    2. URL matches jobs.ashbyhq.com/{slug} or ashbyhq.com/{slug} → extract slug.

Add a source like:
    {"name": "Paradigm Portfolio", "url": "https://jobs.paradigm.xyz/",
     "ashby_slug": "paradigm", "category": "VC_Board"}
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "ashby"

_ASHBY_URL = re.compile(
    r"https?://(?:jobs\.)?ashbyhq\.com/(?P<slug>[a-z0-9\-_]+)",
    re.IGNORECASE,
)

_ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _extract_slug(source: dict) -> str | None:
    # Explicit override wins.
    slug = source.get("ashby_slug")
    if slug:
        return str(slug).strip()
    m = _ASHBY_URL.search(source.get("url", ""))
    return m.group("slug") if m else None


def can_parse(source: dict) -> bool:
    return _extract_slug(source) is not None


def _parse_compensation(comp) -> tuple[int | None, int | None, str | None]:
    """Ashby compensationTierSummary is a string like '$150K – $200K USD';
    compensationTiers is a list of {currency, minValue, maxValue}."""
    if not comp:
        return (None, None, None)
    tiers = comp if isinstance(comp, list) else [comp]
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        # L4: strip + upper before the allow-check so the string "None"
        # (which APIs sometimes return instead of Python None) doesn't
        # escape the filter as "NONE".  The old set included Python None,
        # which was dead code because the `or ""` fallback always yields a
        # str; replaced with "NONE" to cover the string-sentinel case.
        _currency = (tier.get("currencyCode") or tier.get("currency") or "").strip().upper()
        if _currency not in ("USD", "", "NONE"):
            continue
        mn = tier.get("minValue") or tier.get("min")
        mx = tier.get("maxValue") or tier.get("max")
        if isinstance(mn, (int, float)) and isinstance(mx, (int, float)) and 0 < mn <= mx:
            return (int(mn), int(mx), "listed")
    return (None, None, None)


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source)
    if not slug:
        return []
    api_url = _ASHBY_API.format(slug=slug)
    resp = session.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"ashby API {resp.status_code} for slug={slug}")

    # Some boards return 200 with an empty body or an HTML challenge page when
    # the board has been shut down or moved.  Return [] so the source counts as
    # success (jobs_found=0) instead of accumulating consecutive_failures.
    body = (resp.text or "").strip()
    if not body:
        import sys
        print(f"  [ashby] empty body for slug={slug}, skipping", file=sys.stderr)
        return []
    try:
        payload = resp.json() or {}
    except ValueError:
        import sys
        snippet = body[:80].replace("\n", " ")
        print(f"  [ashby] non-JSON for slug={slug}: {snippet!r}, skipping", file=sys.stderr)
        return []
    jobs = payload.get("jobs") or []

    # Multi-org boards (VC portfolio boards) embed the hiring company name in
    # each posting rather than in the source name — prefer that when present.
    board_company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for post in jobs:
        title = (post.get("title") or "").strip()
        if not title:
            continue
        apply_url = post.get("jobUrl") or post.get("applyUrl") or post.get("externalLink")
        if not apply_url:
            continue

        # Multi-org Ashby boards include a nested "organization" object.
        org = post.get("organization") or {}
        company = (org.get("name") or board_company).strip()

        location = post.get("locationName") or post.get("location") or None
        description = post.get("descriptionPlain") or post.get("descriptionHtml") or ""
        # Audit L8: ``startswith("<")`` missed HTML with a BOM, whitespace,
        # or newline prefix. Strip leading whitespace before testing.
        if description.lstrip().startswith("<"):
            import re as _re
            description = _re.sub(r"<[^>]+>", " ", description)
            description = _re.sub(r"\s+", " ", description)
        description = description.strip()[:5000] or None

        comp_tiers = post.get("compensationTiers") or post.get("compensation")
        sal_min, sal_max, sal_src = _parse_compensation(comp_tiers)

        out.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "apply_url": apply_url,
            "source_url": source["url"],
            "salary_min_usd": sal_min,
            "salary_max_usd": sal_max,
            "salary_source": sal_src,
            "category": category,
        })

    return out
