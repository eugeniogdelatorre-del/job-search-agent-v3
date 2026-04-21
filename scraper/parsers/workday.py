"""Workday parser.

Workday job boards expose a public POST JSON API:
    POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    body: {"limit": 20, "offset": 0, "searchText": ""}
Response has `jobPostings` with {title, externalPath, locationsText, postedOn}.

URL shapes we handle:
    https://{tenant}.wd{N}.myworkdayjobs.com/{site}
    https://{tenant}.wd{N}.myworkdayjobs.com/en-US/{site}
    https://{tenant}.wd{N}.myworkdayjobs.com/{locale}/{site}

Descriptions aren't in the list API — fetching one per job would burn
5x the requests. We leave `description=None` and let the classifier /
cv_score agent follow `apply_url` downstream if needed.
"""
from __future__ import annotations

import re

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "workday"

_WORKDAY_URL = re.compile(
    r"https?://(?P<tenant>[a-z0-9\-]+)\.wd(?P<wd>\d+)\.myworkdayjobs\.com/"
    r"(?:(?P<locale>[a-z]{2}-[A-Z]{2})/)?"
    r"(?P<site>[a-zA-Z0-9\-_]+)",
)

PAGE_LIMIT = 20
MAX_PAGES = 5  # cap at 100 jobs per source to bound runtime


def _parse_url(url: str) -> tuple[str, str, str] | None:
    """Returns (tenant, wd_num, site) or None."""
    m = _WORKDAY_URL.search(url or "")
    if not m:
        return None
    return (m.group("tenant"), m.group("wd"), m.group("site"))


def can_parse(source: dict) -> bool:
    return _parse_url(source.get("url", "")) is not None


def parse(session: requests.Session, source: dict) -> list[dict]:
    parsed = _parse_url(source["url"])
    if not parsed:
        return []
    tenant, wd_num, site = parsed
    api_url = f"https://{tenant}.wd{wd_num}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    public_base = f"https://{tenant}.wd{wd_num}.myworkdayjobs.com/en-US/{site}"

    company = source.get("name") or tenant
    category = source.get("category")

    out: list[dict] = []
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    for page in range(MAX_PAGES):
        body = {"limit": PAGE_LIMIT, "offset": page * PAGE_LIMIT, "searchText": ""}
        resp = session.post(api_url, json=body, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            if page == 0:
                raise RuntimeError(f"workday API {resp.status_code} for {tenant}/{site}")
            break
        payload = resp.json() or {}
        postings = payload.get("jobPostings") or []
        if not postings:
            break
        for post in postings:
            title = (post.get("title") or "").strip()
            if not title:
                continue
            external_path = post.get("externalPath") or ""
            if not external_path:
                continue
            apply_url = f"{public_base}{external_path}"
            location = post.get("locationsText") or None
            out.append({
                "title": title,
                "company": company,
                "location": location,
                "description": None,
                "apply_url": apply_url,
                "source_url": source["url"],
                "salary_min_usd": None,
                "salary_max_usd": None,
                "salary_source": None,
                "category": category,
            })
        if len(postings) < PAGE_LIMIT:
            break

    return out
