"""Greenhouse boards parser.

Uses the public Boards API:
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
    https://boards-api.eu.greenhouse.io/v1/boards/{slug}/jobs?content=true  (EU)

Slug extraction handles these URL shapes:
    https://boards.greenhouse.io/{slug}
    https://boards.eu.greenhouse.io/{slug}
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
    r"|boards(?:-api)?\.eu\.greenhouse\.io/(?P<slug4>[a-z0-9\-]+)"
    r")",
    re.IGNORECASE,
)

_US_API_BASE = "https://boards-api.greenhouse.io"
_EU_API_BASE = "https://boards-api.eu.greenhouse.io"


def _extract_slug(url: str) -> tuple[str | None, bool]:
    """Return (slug, is_eu). is_eu=True when the URL uses the EU-hosted board."""
    m = _GREENHOUSE_URL.search(url or "")
    if not m:
        return None, False
    slug = m.group("slug1") or m.group("slug2") or m.group("slug3") or m.group("slug4")
    is_eu = m.group("slug4") is not None
    return slug, is_eu


def can_parse(source: dict) -> bool:
    slug, _ = _extract_slug(source.get("url", ""))
    return slug is not None


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug, is_eu = _extract_slug(source["url"])
    if not slug:
        return []
    api_base = _EU_API_BASE if is_eu else _US_API_BASE
    api_url = f"{api_base}/v1/boards/{slug}/jobs?content=true"
    resp = session.get(api_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
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
    no_tags = re.sub(r"<[^>]+>", " ", html)
    no_tags = (
        no_tags.replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\s+", " ", no_tags).strip()
