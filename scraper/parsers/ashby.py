"""Ashby HQ parser.

Uses the public Job Board API:
    https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true

Slug extraction handles these URL shapes:
    https://jobs.ashbyhq.com/{slug}
    https://jobs.ashbyhq.com/{slug}/...
    https://ashbyhq.com/{slug}
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


def _extract_slug(url: str) -> str | None:
    m = _ASHBY_URL.search(url or "")
    if not m:
        return None
    return m.group("slug")


def can_parse(source: dict) -> bool:
    return _extract_slug(source.get("url", "")) is not None


def _parse_compensation(comp) -> tuple[int | None, int | None, str | None]:
    """Ashby compensationTierSummary is a string like '$150K – $200K USD';
    compensationTiers is a list of {currency, minValue, maxValue}."""
    if not comp:
        return (None, None, None)
    tiers = comp if isinstance(comp, list) else [comp]
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        if (tier.get("currencyCode") or tier.get("currency") or "").upper() not in ("USD", "", None):
            continue
        mn = tier.get("minValue") or tier.get("min")
        mx = tier.get("maxValue") or tier.get("max")
        if isinstance(mn, (int, float)) and isinstance(mx, (int, float)) and 0 < mn <= mx:
            return (int(mn), int(mx), "listed")
    return (None, None, None)


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source["url"])
    if not slug:
        return []
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    resp = session.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"ashby API {resp.status_code} for slug={slug}")

    payload = resp.json() or {}
    jobs = payload.get("jobs") or []
    company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for post in jobs:
        title = (post.get("title") or "").strip()
        if not title:
            continue
        apply_url = post.get("jobUrl") or post.get("applyUrl") or post.get("externalLink")
        if not apply_url:
            continue
        location = post.get("locationName") or post.get("location") or None
        description = (post.get("descriptionPlain") or post.get("descriptionHtml") or "")
        # descriptionHtml contains HTML; trim if we fell back to it.
        if description.startswith("<"):
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
