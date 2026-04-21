"""Greenhouse boards parser.

Uses the public Boards API:
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

Slug extraction handles these v2 URL shapes:
    https://boards.greenhouse.io/{slug}
    https://boards.greenhouse.io/{slug}/jobs/...
    https://{slug}.greenhouse.io/...
    https://jobs.greenhouse.io/{slug}

If the URL doesn't look like a Greenhouse board, `can_parse` returns False
and the orchestrator moves on.
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "greenhouse"


_GREENHOUSE_URL = re.compile(
    r"https?://(?:"
    r"boards(?:-api)?\.greenhouse\.io/(?P<slug1>[a-z0-9\-]+)"
    r"|jobs\.greenhouse\.io/(?P<slug2>[a-z0-9\-]+)"
    r"|(?P<slug3>[a-z0-9\-]+)\.greenhouse\.io"
    r")",
    re.IGNORECASE,
)


def _extract_slug(url: str) -> str | None:
    m = _GREENHOUSE_URL.search(url or "")
    if not m:
        return None
    return m.group("slug1") or m.group("slug2") or m.group("slug3")


def can_parse(source: dict) -> bool:
    return _extract_slug(source.get("url", "")) is not None


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source["url"])
    if not slug:
        return []
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    resp = session.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        # Surface the status to the caller via exception so sources_health records the failure.
        raise RuntimeError(f"greenhouse API {resp.status_code} for slug={slug}")

    payload = resp.json()
    company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for job in payload.get("jobs", []):
        title = (job.get("title") or "").strip()
        if not title:
            continue
        location = (job.get("location") or {}).get("name")
        apply_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{slug}/jobs/{job.get('id')}"
        content_html = job.get("content") or ""
        # Greenhouse returns HTML-encoded content; strip tags quick-and-dirty.
        description = _strip_html(content_html)[:5000] if content_html else None

        out.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "apply_url": apply_url,
            "source_url": source["url"],
            "salary_min_usd": None,
            "salary_max_usd": None,
            "salary_source": None,
            "category": category,
        })

    return out


def _strip_html(html: str) -> str:
    # Avoid pulling bs4 for hot-path strip; scrape.py uses bs4 for HTML parsers
    # but here the Greenhouse API gives us already-cleanish HTML. Cheap regex strip.
    no_tags = re.sub(r"<[^>]+>", " ", html)
    # Decode a handful of common entities without the html module overhead.
    no_tags = (
        no_tags.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", no_tags).strip()
