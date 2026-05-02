"""web3.career parser.

Two modes:

1. **API mode (preferred)** — when ``WEB3_CAREER_API_KEY`` is set in the
   environment, fetch from the official endpoint
   ``https://web3.career/api/v1?token=KEY&limit=100`` (registered at
   ``web3.career/web3-jobs-api``). Quirks of the response shape:
       - The body is a mixed-type JSON array; the jobs live inside the
         first array element nested within the root array (per the
         official docs). We scan defensively for that.
       - Each job dict's field names are not strictly schemed; we read
         ``title`` / ``company`` / ``location`` / ``description`` /
         ``apply_url`` (or ``url``) / ``salary``, falling back to
         alternates where common ones exist.

2. **HTML fallback** — when the API key is missing, scrape the rendered
   table at ``https://web3.career/`` (or whatever URL is in
   ``sources.json``). Each ``<tr data-jobid=...>`` has six ``<td>``s in
   order: title, company, age, location, salary, tags.

The fallback exists so the parser keeps producing rows if Eugenio
forgets to add the secret in GitHub Actions, instead of going dark
silently. Once the key is in place, the API path covers far more
listings (27k+ vs. ~20 on the homepage) and is more stable.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import REQUEST_TIMEOUT_SECONDS

name = "web3career"

W3C_HOST = "web3.career"
W3C_API_URL = "https://web3.career/api/v1"
W3C_API_LIMIT = 100  # API max per call

_ONCLICK_URL_RE = re.compile(r"tableTurboRowClick\(event,\s*['\"]([^'\"]+)['\"]\)")
_SALARY_RE = re.compile(
    r"\$\s*([\d]+)\s*k?\s*[-–]\s*\$?\s*([\d]+)\s*k?",
    re.IGNORECASE,
)


def can_parse(source: dict) -> bool:
    return W3C_HOST in (source.get("url") or "").lower()


def _parse_salary(s: str) -> tuple[int | None, int | None, str | None]:
    if not s:
        return (None, None, None)
    m = _SALARY_RE.search(s)
    if not m:
        return (None, None, None)
    lo = int(m.group(1))
    hi = int(m.group(2))
    if "k" in s.lower():
        lo *= 1000
        hi *= 1000
    if 0 < lo <= hi <= 2_000_000 and lo >= 10_000:
        return (lo, hi, "listed")
    return (None, None, None)


def _find_jobs_array(payload):
    """Locate the jobs list inside a mixed-type array response.

    Per the official docs the root is shaped like ``[meta, meta, [job, job, ...]]``;
    we scan for the first list-of-dicts to be defensive against schema drift.
    """
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, list) and item and isinstance(item[0], dict):
                return item
        # Some plans return a flat list of jobs directly — handle that too.
        if payload and isinstance(payload[0], dict):
            return payload
    if isinstance(payload, dict):
        # Defensive: some APIs wrap under {"data": [...]} or {"jobs": [...]}.
        for key in ("jobs", "data", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []


def _coerce_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _job_from_api(item: dict, source_url: str, category: str) -> dict | None:
    title = _coerce_str(item.get("title") or item.get("job_title") or item.get("name"))
    if not title:
        return None
    company = (
        _coerce_str(item.get("company") or item.get("company_name") or item.get("employer"))
        or "Unknown"
    )
    location = _coerce_str(item.get("location") or item.get("country") or item.get("city")) or None
    apply_url = _coerce_str(item.get("apply_url") or item.get("url") or item.get("link")) or source_url
    description = _coerce_str(item.get("description") or item.get("summary"))[:5000] or None

    sal_min, sal_max, sal_src = (None, None, None)
    salary_field = item.get("salary")
    if isinstance(salary_field, str) and salary_field:
        sal_min, sal_max, sal_src = _parse_salary(salary_field)
    elif isinstance(salary_field, dict):
        # Some responses break salary into min/max numeric fields.
        try:
            lo = int(salary_field.get("min") or salary_field.get("from") or 0) or None
            hi = int(salary_field.get("max") or salary_field.get("to") or 0) or None
        except (TypeError, ValueError):
            lo, hi = None, None
        if lo and hi and 0 < lo <= hi <= 2_000_000 and lo >= 10_000:
            sal_min, sal_max, sal_src = lo, hi, "listed"
    else:
        # Numeric pair fields seen on some plans.
        try:
            lo = item.get("salary_min") or item.get("salary_from")
            hi = item.get("salary_max") or item.get("salary_to")
            lo_i = int(lo) if lo is not None else None
            hi_i = int(hi) if hi is not None else None
        except (TypeError, ValueError):
            lo_i, hi_i = None, None
        if lo_i and hi_i and 0 < lo_i <= hi_i <= 2_000_000 and lo_i >= 10_000:
            sal_min, sal_max, sal_src = lo_i, hi_i, "listed"

    return {
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "apply_url": apply_url,
        "source_url": source_url,
        "salary_min_usd": sal_min,
        "salary_max_usd": sal_max,
        "salary_source": sal_src,
        "category": category,
        "_discovery_channel": "Web3.career",
    }


def _parse_via_api(session: requests.Session, source: dict, token: str) -> list[dict]:
    params = {"token": token, "limit": W3C_API_LIMIT, "show_description": "true"}
    resp = session.get(W3C_API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    if resp.status_code == 429:
        raise RuntimeError("web3.career API 429 (rate limited) — back off and retry next cron")
    if resp.status_code != 200:
        raise RuntimeError(f"web3.career API {resp.status_code}: {resp.text[:200]!r}")
    try:
        payload = resp.json()
    except ValueError as e:
        raise RuntimeError(f"web3.career API JSON parse error: {e}")

    jobs = _find_jobs_array(payload)
    source_url = source.get("url") or "https://web3.career/"
    category = source.get("category") or "Board"

    out: list[dict] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        row = _job_from_api(item, source_url, category)
        if row is not None:
            out.append(row)
    return out


def _parse_via_html(session: requests.Session, source: dict) -> list[dict]:
    url = source["url"]
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"web3.career {resp.status_code} for {url}")

    soup = BeautifulSoup(resp.text, "lxml")
    rows = soup.select("tr[data-jobid]")
    if not rows:
        return []

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    category = source.get("category") or "Board"
    source_name = source.get("name") or "Web3.career"

    out: list[dict] = []
    for row in rows:
        tds = row.find_all("td", recursive=False)
        if len(tds) < 5:
            continue
        title = tds[0].get_text(" ", strip=True)
        company = tds[1].get_text(" ", strip=True)
        location = tds[3].get_text(" ", strip=True) if len(tds) >= 4 else None
        salary_str = tds[4].get_text(" ", strip=True) if len(tds) >= 5 else ""
        tags = tds[5].get_text(" ", strip=True) if len(tds) >= 6 else ""

        if not title or not company:
            continue

        onclick = row.get("onclick") or ""
        m = _ONCLICK_URL_RE.search(onclick)
        apply_url = (base + m.group(1)) if m else url

        sal_min, sal_max, sal_src = _parse_salary(salary_str)

        out.append({
            "title": title,
            "company": company,
            "location": location or None,
            "description": tags[:500] or None,
            "apply_url": apply_url,
            "source_url": url,
            "salary_min_usd": sal_min,
            "salary_max_usd": sal_max,
            "salary_source": sal_src,
            "category": category,
            "_discovery_channel": source_name if source_name.lower() == "web3.career" else None,
        })

    return out


def parse(session: requests.Session, source: dict) -> list[dict]:
    token = os.environ.get("WEB3_CAREER_API_KEY")
    if token:
        return _parse_via_api(session, source, token)
    return _parse_via_html(session, source)
