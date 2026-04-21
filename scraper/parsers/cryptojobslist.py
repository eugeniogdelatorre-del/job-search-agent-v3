"""CryptoJobsList parser.

The site is Next.js SSR. Each category/homepage URL embeds the first ~25
jobs in a `<script id="__NEXT_DATA__">` JSON blob. Direct API calls to
api.cryptojobslist.com are Cloudflare-blocked, so we scrape the page HTML
and parse the embedded data.

Company-specific URLs (`/companies/{slug}`) render their jobs client-side
via the API, so the embedded blob has no jobs. Those pages return [].

URL shapes we handle:
    https://cryptojobslist.com/               (homepage)
    https://cryptojobslist.com/{category}     (category, e.g. /marketing)
    https://cryptojobslist.com/companies/...  (company page — returns [])
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "cryptojobslist"

CJL_HOST = "cryptojobslist.com"

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
    re.DOTALL,
)


def can_parse(source: dict) -> bool:
    return CJL_HOST in (source.get("url") or "").lower()


def _extract_next_data(html: str) -> dict | None:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


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


def parse(session: requests.Session, source: dict) -> list[dict]:
    url = source["url"]
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"cryptojobslist {resp.status_code} for {url}")

    data = _extract_next_data(resp.text)
    if not data:
        return []

    jobs_raw = (
        data.get("props", {})
            .get("pageProps", {})
            .get("jobs", [])
    )

    parsed_host = urlparse(url)
    source_name = source.get("name") or "CryptoJobsList"
    category = source.get("category") or "Board"

    out: list[dict] = []
    for j in jobs_raw:
        if not j.get("isActive", True):
            continue
        if j.get("filled"):
            continue
        title = (j.get("jobTitle") or "").strip()
        company = (j.get("companyName") or "").strip()
        if not title or not company:
            continue

        seo_slug = j.get("seoSlug") or j.get("companySlug")
        apply_url = f"{parsed_host.scheme}://{parsed_host.netloc}/jobs/{seo_slug}" if seo_slug else url

        location_obj = j.get("jobLocation") or {}
        if isinstance(location_obj, dict):
            location = location_obj.get("name") or location_obj.get("city") or location_obj.get("country")
        else:
            location = str(location_obj) if location_obj else None
        if not location and j.get("remote"):
            location = "Remote"

        sal_min, sal_max, sal_src = _salary_fields(j)

        tags = j.get("tags") or []
        tag_str = ", ".join(t for t in tags if isinstance(t, str))[:500]

        out.append({
            "title": title,
            "company": company,
            "location": location,
            "description": tag_str or None,
            "apply_url": apply_url,
            "source_url": url,
            "salary_min_usd": sal_min,
            "salary_max_usd": sal_max,
            "salary_source": sal_src,
            "category": category,
            "_discovery_channel": source_name if source_name.lower() == "cryptojobslist" else None,
        })

    return out
