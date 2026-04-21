"""web3.career parser.

The site ships an HTML table of jobs. Each <tr data-jobid=...> has six
<td>s in order: title, company, age, location, salary, tags. The onclick
attribute holds the relative job URL.

URL shapes we handle:
    https://web3.career/               (homepage, ~20 rows)
    https://web3.career/{category}     (category pages)
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import REQUEST_TIMEOUT_SECONDS

name = "web3career"

W3C_HOST = "web3.career"

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


def parse(session: requests.Session, source: dict) -> list[dict]:
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
