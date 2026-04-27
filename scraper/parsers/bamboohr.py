"""BambooHR careers parser.

Uses the public BambooHR careers API:
    GET https://{slug}.bamboohr.com/careers/list   -> list of open jobs
    GET https://{slug}.bamboohr.com/careers/{id}/detail -> full JD

slug is the company subdomain: acme.bamboohr.com -> slug=acme
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "bamboohr"

_BAMBOOHR_URL = re.compile(
    r"https?://(?P<slug>[a-z0-9\-]+)\.bamboohr\.com",
    re.IGNORECASE,
)


def _extract_slug(url: str) -> str | None:
    m = _BAMBOOHR_URL.search(url or "")
    return m.group("slug") if m else None


def can_parse(source: dict) -> bool:
    return _extract_slug(source.get("url", "")) is not None


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source["url"])
    if not slug:
        return []

    list_url = f"https://{slug}.bamboohr.com/careers/list"
    resp = session.get(list_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"bamboohr list API {resp.status_code} for slug={slug}")

    payload = resp.json() or {}
    items = payload.get("result") or []
    company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for item in items:
        job_id = item.get("id")
        title = (item.get("jobOpeningName") or "").strip()
        if not job_id or not title:
            continue

        detail_url = f"https://{slug}.bamboohr.com/careers/{job_id}/detail"
        detail: dict = {}
        try:
            detail_resp = session.get(detail_url, timeout=REQUEST_TIMEOUT_SECONDS)
            if detail_resp.status_code == 200:
                detail = (detail_resp.json() or {}).get("result", {}).get("jobOpening") or {}
        except Exception:
            pass

        if not detail:
            out.append({
                "title": title,
                "company": company,
                "location": None,
                "description": None,
                "apply_url": detail_url,
                "source_url": source["url"],
                "salary_min_usd": None,
                "salary_max_usd": None,
                "salary_source": None,
                "category": category,
            })
            continue

        raw_location = detail.get("location") or {}
        if isinstance(raw_location, dict):
            location: str | None = raw_location.get("name") or raw_location.get("city") or None
        elif isinstance(raw_location, str):
            location = raw_location or None
        else:
            location = None

        description_html = detail.get("description") or ""
        description_text = re.sub(r"<[^>]+>", " ", description_html)
        description_text = re.sub(r"\s+", " ", description_text).strip()
        description: str | None = description_text[:5000] or None

        apply_url: str = detail.get("jobOpeningShareUrl") or detail_url

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
