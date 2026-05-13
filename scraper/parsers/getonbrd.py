"""Get on Board (getonbrd.com) parser.

GoB is the dominant LATAM tech job board: Spanish + English roles,
heavy bias toward remote / LATAM-eligible positions. Single source —
unlike the ATS parsers, one entry in sources.json fetches the whole
board.

API:
    https://www.getonbrd.com/api/v0/categories/programming/jobs?per_page=100&page=N

Each job carries structured fields directly useful for our downstream
classify + score pipeline:
    - title, description (HTML)
    - remote (bool), remote_modality, remote_zone, countries
    - min_salary / max_salary (often MONTHLY USD for LATAM listings —
      we heuristically convert sub-$10k figures by × 12)
    - seniority, tags (relationship IDs — we don't resolve these)
    - company.data.id  (NUMERIC id — must be fetched separately at
      /api/v0/companies/{id} to get the display name)
    - links.public_url  (the apply page)

The company endpoint is one extra request per unique company. We cache
within a single ``parse()`` call so the total extra cost is roughly
unique-companies-per-day (~100), not jobs-per-day (~500).

Add a single source like:
    {"name": "Get on Board", "url": "https://www.getonbrd.com/jobs",
     "category": "LATAM_Board"}
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "getonbrd"

# Match any getonbrd.com URL. Sufficient identifier — the parser pulls
# from a fixed API endpoint regardless of the source URL the operator
# pasted.
_URL_RE = re.compile(r"https?://(?:www\.)?getonbrd\.com", re.IGNORECASE)

_JOBS_API = "https://www.getonbrd.com/api/v0/categories/programming/jobs"
_COMPANY_API = "https://www.getonbrd.com/api/v0/companies/{id}"

PAGE_LIMIT = 100
MAX_PAGES = 5  # 500 jobs cap per source — same shape as workday.py

# LATAM listings frequently quote salary in monthly USD instead of
# annual. If both bounds are this low or below, we treat as monthly
# and annualize × 12 so downstream score.py compares apples to apples
# against the new SALARY_BAND_MIN_USD = $30k / MAX = $120k band.
_MONTHLY_USD_THRESHOLD = 10_000


def can_parse(source: dict) -> bool:
    return _URL_RE.search(source.get("url", "")) is not None


def _strip_html(text: str) -> str:
    if not text:
        return ""
    if text.lstrip().startswith("<"):
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
    return text.strip()[:5000]


def _normalize_salary(min_v, max_v) -> tuple[int | None, int | None]:
    """Convert min/max salary into annual USD.

    GoB exposes salary in two forms across listings — annual USD for
    senior + US-remote roles, monthly USD for many LATAM roles. We
    can't distinguish reliably from the API, so heuristic: if BOTH
    bounds are <= $10k, treat as monthly and × 12. Otherwise annual.
    """
    def _i(v):
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    lo, hi = _i(min_v), _i(max_v)
    if lo is None and hi is None:
        return (None, None)
    # If max is below threshold (and present), treat both as monthly.
    if hi is not None and hi <= _MONTHLY_USD_THRESHOLD:
        lo = lo * 12 if lo else lo
        hi = hi * 12
    return (lo, hi)


def _build_location(attrs: dict, company_name: str) -> str | None:
    """Best-effort human-readable location string.

    GoB's location_cities / location_regions are relationship objects
    (id-only). The plain `countries` array is a simple string list and
    usually says "Remote" or a country name.
    """
    if attrs.get("remote"):
        countries = attrs.get("countries") or []
        if countries and countries != ["Remote"]:
            return f"Remote — {', '.join(countries[:3])}"
        return "Remote"
    countries = attrs.get("countries") or []
    return ", ".join(countries[:3]) if countries else None


def _fetch_company_name(session: requests.Session, company_id: str, cache: dict) -> str:
    """Resolve numeric company id → display name. Caches per parse() call."""
    if not company_id:
        return ""
    if company_id in cache:
        return cache[company_id]
    try:
        r = session.get(
            _COMPANY_API.format(id=company_id),
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            cache[company_id] = ""
            return ""
        payload = r.json() or {}
        attrs = (payload.get("data") or {}).get("attributes") or {}
        name = (attrs.get("name") or "").strip()
        cache[company_id] = name
        return name
    except Exception:
        cache[company_id] = ""
        return ""


def parse(session: requests.Session, source: dict) -> list[dict]:
    out: list[dict] = []
    category = source.get("category")
    company_cache: dict[str, str] = {}

    for page in range(1, MAX_PAGES + 1):
        params = {"per_page": PAGE_LIMIT, "page": page}
        resp = session.get(
            _JOBS_API,
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            if page == 1:
                raise RuntimeError(f"getonbrd API {resp.status_code}")
            break
        payload = resp.json() or {}
        jobs = payload.get("data") or []
        if not jobs:
            break

        for job in jobs:
            attrs = job.get("attributes") or {}
            title = (attrs.get("title") or "").strip()
            if not title:
                continue

            links = job.get("links") or {}
            apply_url = links.get("public_url")
            if not apply_url:
                continue

            company_rel = (attrs.get("company") or {}).get("data") or {}
            company_id = str(company_rel.get("id") or "")
            company = _fetch_company_name(session, company_id, company_cache) or "Unknown"

            description = _strip_html(attrs.get("description") or "")
            sal_lo, sal_hi = _normalize_salary(attrs.get("min_salary"), attrs.get("max_salary"))
            sal_src = "listed" if (sal_lo or sal_hi) else None

            out.append({
                "title": title,
                "company": company,
                "location": _build_location(attrs, company),
                "description": description or None,
                "apply_url": apply_url,
                "source_url": source["url"],
                "salary_min_usd": sal_lo,
                "salary_max_usd": sal_hi,
                "salary_source": sal_src,
                "category": category,
            })

        meta = payload.get("meta") or {}
        total_pages = int(meta.get("total_pages") or 0)
        if total_pages and page >= total_pages:
            break

    return out
