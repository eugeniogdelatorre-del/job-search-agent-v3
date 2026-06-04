"""Lever postings parser.

Uses the public postings API:
    https://api.lever.co/v0/postings/{slug}?mode=json

Slug extraction handles these URL shapes:
    https://jobs.lever.co/{slug}
    https://jobs.lever.co/{slug}/...
    https://{slug}.lever.co/...
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "lever"


# Lever marketing paths that live on the bare lever.co/<path> domain and are
# NOT job boards. The bare-domain branch excludes these so they don't get sent
# to api.lever.co (404 → source marked failed). Real bare-domain boards (e.g.
# lever.co/Onehouse) still match because their slug isn't in this set.
_LEVER_RESERVED = (
    r"about|blog|customers|pricing|login|contact|careers|platform|product|"
    r"resources|company|legal|privacy|terms|demo|plans|index|home|features|"
    r"integrations|security|partners|press|events|support|help|status|api|"
    r"developers|docs|solutions|customer-stories|request-demo"
)

_LEVER_URL = re.compile(
    r"https?://(?:"
    r"jobs\.lever\.co/(?P<slug1>[a-zA-Z0-9\-_]+)"
    r"|(?:www\.)?lever\.co/(?!(?:" + _LEVER_RESERVED + r")(?:[/?#]|$))(?P<slug3>[a-zA-Z0-9\-_]+)"
    r"|(?!www\.)(?P<slug2>[a-zA-Z0-9\-_]+)\.lever\.co"
    r")",
    re.IGNORECASE,
)


def _extract_slug(url: str) -> str | None:
    m = _LEVER_URL.search(url or "")
    if not m:
        return None
    return m.group("slug1") or m.group("slug2") or m.group("slug3")


def can_parse(source: dict) -> bool:
    return _extract_slug(source.get("url", "")) is not None


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source["url"])
    if not slug:
        return []
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    resp = session.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"lever API {resp.status_code} for slug={slug}")

    payload = resp.json()
    company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for post in payload:
        title = (post.get("text") or "").strip()
        if not title:
            continue
        categories = post.get("categories") or {}
        location = categories.get("location")
        apply_url = post.get("hostedUrl") or post.get("applyUrl")
        if not apply_url:
            continue
        description = (post.get("descriptionPlain") or post.get("description") or "")[:5000] or None
        salary = post.get("salaryRange") or {}
        # Audit H4 (2026-05-20): gate on currency so GBP/EUR amounts are not
        # stored as if they were USD. Empty string and absent currency are treated
        # as USD (common in older Lever postings). Case-insensitive comparison.
        currency = (salary.get("currency") or "").strip().upper()
        if currency in ("", "USD"):
            salary_min = salary.get("min")
            salary_max = salary.get("max")
            salary_source = "listed" if (salary_min or salary_max) else None
        else:
            salary_min = None
            salary_max = None
            salary_source = None

        out.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "apply_url": apply_url,
            "source_url": source["url"],
            "salary_min_usd": int(salary_min) if isinstance(salary_min, (int, float)) else None,
            "salary_max_usd": int(salary_max) if isinstance(salary_max, (int, float)) else None,
            "salary_source": salary_source,
            "category": category,
        })

    return out
