"""CryptoJobsList parser.

Two parse paths:

1. JSON feed — https://cryptojobslist.com/jobs.json
   Public endpoint returning all recent jobs in one request. Preferred.
   Response is either [{...}, ...] or {"jobs": [{...}, ...]}.

2. HTML scrape — any other cryptojobslist.com URL (homepage / category pages)
   The site is Next.js SSR. Each page embeds jobs in a
   <script id="__NEXT_DATA__"> JSON blob which we extract.
   Company-specific URLs (/companies/{slug}) render client-side and
   return no jobs from this path — they are intentionally removed from
   sources.json in favour of the JSON feed above.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "cryptojobslist"

CJL_HOST = "cryptojobslist.com"
JSON_FEED_PATH = "/jobs.json"

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


def can_parse(source: dict) -> bool:
    return CJL_HOST in (source.get("url") or "").lower()


def _salary_fields(raw: dict) -> tuple[int | None, int | None, str | None]:
    salary = raw.get("salary") or {}
    if not isinstance(salary, dict):
        return (None, None, None)
    if (salary.get("currency") or "").upper() not in ("USD", "", None):
        return (None, None, None)
    mn = salary.get("minValue")
    mx = salary.get("maxValue")
    if isinstance(mn, (int, float)) and isinstance(mx, (int, float)) and 0 < mn <= mx:
        return (int(mn), int(mx), "listed")
    return (None, None, None)


def _job_from_raw(j: dict, source_url: str, source_name: str) -> dict | None:
    """Normalise a single job dict from either the feed or the HTML blob."""
    if not isinstance(j, dict):
        return None
    # Audit L9: previously defaulted ``isActive`` to True on missing key.
    # If CJL renames it to `is_active`/`active` (already inconsistent
    # between the JSON feed and the HTML blob), every filled job would
    # leak through. Check all known spellings and default to True only
    # when none are present, so a real "active=false" still wins.
    active_value = j.get("isActive")
    if active_value is None:
        active_value = j.get("is_active")
    if active_value is None:
        active_value = j.get("active")
    if active_value is False:
        return None
    if j.get("filled"):
        return None

    # Field names vary slightly between the JSON feed and the __NEXT_DATA__ blob.
    title = (
        j.get("jobTitle") or j.get("title") or j.get("job_title") or ""
    ).strip()
    company = (
        j.get("companyName") or j.get("company") or j.get("company_name") or ""
    ).strip()
    if not title or not company:
        return None

    seo_slug = j.get("seoSlug") or j.get("slug") or j.get("companySlug")
    parsed = urlparse(source_url)
    apply_url = (
        f"{parsed.scheme}://{parsed.netloc}/jobs/{seo_slug}"
        if seo_slug
        else source_url
    )

    location_obj = j.get("jobLocation") or j.get("location") or {}
    if isinstance(location_obj, dict):
        location = (
            location_obj.get("name")
            or location_obj.get("city")
            or location_obj.get("country")
        )
    else:
        location = str(location_obj) if location_obj else None
    if not location and j.get("remote"):
        location = "Remote"

    sal_min, sal_max, sal_src = _salary_fields(j)

    tags = j.get("tags") or []
    tag_str = ", ".join(t for t in tags if isinstance(t, str))[:500]

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": tag_str or None,
        "apply_url": apply_url,
        "source_url": source_url,
        "salary_min_usd": sal_min,
        "salary_max_usd": sal_max,
        "salary_source": sal_src,
        "_cjl_company": company,  # used by scrape.py boost logic
    }


_HTML_FALLBACK_URL = "https://cryptojobslist.com/"


def _parse_json_feed(session: requests.Session, source: dict) -> list[dict]:
    url = source["url"]
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    # Cryptojobslist started returning 403 on the JSON feed for non-browser
    # User-Agents. Fall back to scraping the homepage's __NEXT_DATA__ blob
    # rather than failing the whole source.
    if resp.status_code == 403:
        fallback_source = {
            **source,
            "url": _HTML_FALLBACK_URL,
            "name": source.get("name") or "CryptoJobsList",
        }
        return _parse_html(session, fallback_source)
    if resp.status_code != 200:
        raise RuntimeError(f"cryptojobslist JSON feed {resp.status_code} for {url}")

    try:
        data = resp.json()
    except ValueError:
        # Some 200 responses are HTML challenge pages — try the HTML fallback
        # before giving up entirely.
        fallback_source = {
            **source,
            "url": _HTML_FALLBACK_URL,
            "name": source.get("name") or "CryptoJobsList",
        }
        return _parse_html(session, fallback_source)

    if isinstance(data, list):
        jobs_raw = data
    elif isinstance(data, dict):
        # {"jobs": [...]} or {"data": [...]}
        jobs_raw = data.get("jobs") or data.get("data") or []
    else:
        return []

    out: list[dict] = []
    for j in jobs_raw:
        job = _job_from_raw(j, url, source.get("name") or "CryptoJobsList")
        if job:
            out.append(job)
    return out


def _extract_next_data(html: str) -> dict | None:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _parse_html(session: requests.Session, source: dict) -> list[dict]:
    url = source["url"]
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"cryptojobslist {resp.status_code} for {url}")

    data = _extract_next_data(resp.text)
    if not data:
        return []

    jobs_raw = (
        data.get("props", {}).get("pageProps", {}).get("jobs", [])
    )

    out: list[dict] = []
    for j in jobs_raw:
        job = _job_from_raw(j, url, source.get("name") or "CryptoJobsList")
        if job:
            out.append(job)
    return out


def parse(session: requests.Session, source: dict) -> list[dict]:
    url = (source.get("url") or "").rstrip("/")
    if url.endswith(JSON_FEED_PATH):
        return _parse_json_feed(session, source)
    return _parse_html(session, source)
