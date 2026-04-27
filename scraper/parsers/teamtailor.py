"""Teamtailor RSS parser.

Teamtailor job boards publish a standard RSS feed at:
    https://{slug}.teamtailor.com/jobs.rss

slug is the company subdomain: acme.teamtailor.com -> slug=acme
No external dependencies -- uses stdlib xml.etree.ElementTree.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "teamtailor"

_TEAMTAILOR_URL = re.compile(
    r"https?://(?P<slug>[a-z0-9\-]+)\.teamtailor\.com",
    re.IGNORECASE,
)


def _extract_slug(url: str) -> str | None:
    m = _TEAMTAILOR_URL.search(url or "")
    return m.group("slug") if m else None


def can_parse(source: dict) -> bool:
    return _extract_slug(source.get("url", "")) is not None


def _strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", no_tags).strip()


def parse(session: requests.Session, source: dict) -> list[dict]:
    slug = _extract_slug(source["url"])
    if not slug:
        return []

    rss_url = f"https://{slug}.teamtailor.com/jobs.rss"
    resp = session.get(rss_url, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"teamtailor RSS {resp.status_code} for slug={slug}")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise RuntimeError(f"teamtailor RSS parse error for {slug}: {exc}") from exc

    channel = root.find("channel")
    if channel is None:
        return []

    company = source.get("name") or slug
    category = source.get("category")
    out: list[dict] = []

    for item in channel.findall("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")

        title = (title_el.text or "").strip() if title_el is not None else ""
        apply_url = (link_el.text or "").strip() if link_el is not None else ""
        if not title or not apply_url:
            continue

        description: str | None = None
        if desc_el is not None and desc_el.text:
            description = _strip_html(desc_el.text)[:5000] or None

        out.append({
            "title": title,
            "company": company,
            "location": None,
            "description": description,
            "apply_url": apply_url,
            "source_url": source["url"],
            "salary_min_usd": None,
            "salary_max_usd": None,
            "salary_source": None,
            "category": category,
        })

    return out
