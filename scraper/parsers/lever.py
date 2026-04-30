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


_LEVER_URL = re.compile(
    r"https?://(?:"
    r"jobs\.lever\.co/(?P<slug1>[a-zA-Z0-9\-_]+)"
    r"|(?:www\.)?lever\.co/(?P<slug3>[a-zA-Z0-9\-_]+)"
    r"|(?P<slug2>[a-zA-Z0-9\-_]+)\.lever\.co"
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
        salary_min = salary.get("min")
        salary_max = salary.get("max")
        salary_source = "listed" if (salary_min or salary_max) else None

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
