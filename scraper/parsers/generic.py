"""Generic BS4 fallback parser for direct career pages.

Catch-all for sources whose URL doesn't match any dedicated ATS parser.
Ported from v2 `scrape.py` `scrape_career_page` with tighter heuristics to
avoid the sidebar/nav noise that plagued v2.

Conservative: we only emit rows that satisfy BOTH signals
    1. href contains a job-URL marker (/jobs/, /careers/, lever.co/, etc.)
    2. text looks like a job title (role keyword + length range)

If neither strategy yields results, we return []. Precision > recall: we'd
rather miss a source than flood Checkpoint 2 with junk mash-up rows.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import REQUEST_TIMEOUT_SECONDS

name = "generic"

MAX_JOBS_PER_SOURCE = 50
MIN_TITLE_LEN = 8
MAX_TITLE_LEN = 160

JOB_URL_SIGNALS = (
    "/job/", "/jobs/", "/position/", "/role/", "/opening/", "/career/",
    "/careers/", "/vacancy/", "/apply/", "greenhouse.io/", "lever.co/",
    "ashbyhq.com/", "myworkdayjobs.com/", "breezy.hr/",
    "smartrecruiters.com/", "workable.com/", "recruitee.com/",
)

ROLE_KEYWORDS = re.compile(
    r"\b(engineer|developer|manager|lead|director|analyst|designer|"
    r"specialist|coordinator|architect|scientist|consultant|strategist|"
    r"head[\s\-]of|vp[\s\-]of|president|marketing|growth|content|"
    r"social|community|partnerships|sales|bizdev|business[\s\-]development|"
    r"devrel|kol|ambassador|operations|product|research|recruiter|founder|"
    r"counsel|legal|compliance|writer|editor|producer|intern)\b",
    re.IGNORECASE,
)

# Nav/boilerplate phrases that should never be treated as job titles.
NAV_PHRASES = re.compile(
    r"^\s*(about|home|contact|blog|news|press|privacy|terms|careers|"
    r"jobs|login|sign[\s\-]in|subscribe|apply now|learn more|read more|"
    r"see all|view all|explore|discover|welcome|our team|join us)\s*$",
    re.IGNORECASE,
)

# Prefixes that signal a link is a "read more"/"see details" cross-link, not
# a real job title. Drops rows like "Read more about Engineer X at Helius".
JUNK_PREFIXES = re.compile(
    r"^\s*(read\s+more|learn\s+more|view\s+(?:full\s+)?(?:job|role|position)|"
    r"see\s+(?:full\s+)?(?:job|role|description|details)|apply\s+(?:now|here)|"
    r"more\s+info)\b",
    re.IGNORECASE,
)

# Trailing location/work-type badges commonly bled into titles by CSS-merged
# listings (e.g. "Growth Relations Manager Hybrid Available").
TRAILING_BADGE = re.compile(
    r"\s+(remote|hybrid|on[\s\-]?site|full[\s\-]?time|part[\s\-]?time|"
    r"contract|freelance|internship)(\s+(available|role|only))?\s*$",
    re.IGNORECASE,
)


def can_parse(source: dict) -> bool:
    return bool(source.get("url"))


def _clean_title(raw: str) -> str:
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", raw or "")  # drop emojis
    cleaned = re.sub(
        r"\s*[\(\[].*?(remote|hybrid|onsite|full[\s\-]?time|part[\s\-]?time|location).*?[\)\]]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip trailing "Hybrid Available", "Remote Only", etc.
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = TRAILING_BADGE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_like_title(text: str) -> bool:
    if not text:
        return False
    if JUNK_PREFIXES.match(text):
        return False
    if len(text) < MIN_TITLE_LEN or len(text) > MAX_TITLE_LEN:
        return False
    if NAV_PHRASES.match(text):
        return False
    return bool(ROLE_KEYWORDS.search(text))


def _absolute_url(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(base, href)


def parse(session: requests.Session, source: dict) -> list[dict]:
    url = source["url"]
    resp = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"generic {resp.status_code} for {url}")

    soup = BeautifulSoup(resp.text, "lxml")
    company = source.get("name") or urlparse(url).netloc
    category = source.get("category")

    seen_titles: set[str] = set()
    out: list[dict] = []

    for link in soup.find_all("a", href=True):
        if len(out) >= MAX_JOBS_PER_SOURCE:
            break
        href = link["href"]
        text = link.get_text(" ", strip=True)
        if not href or not text:
            continue

        href_lower = href.lower()
        has_url_signal = any(sig in href_lower for sig in JOB_URL_SIGNALS)
        if not has_url_signal:
            continue

        title = _clean_title(text)
        if not _looks_like_title(title):
            continue

        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)

        apply_url = _absolute_url(url, href)

        # Best-effort location/description extraction from the surrounding element.
        parent = link.parent
        location = None
        description = None
        if parent:
            loc_match = parent.find(
                string=re.compile(
                    r"remote|on[\s\-]?site|hybrid|buenos aires|latam|americas|global",
                    re.IGNORECASE,
                )
            )
            if loc_match:
                location = loc_match.strip()[:120]
            desc_el = parent.find(
                ["p", "span", "div"],
                class_=re.compile(r"desc|summary|subtitle|location", re.IGNORECASE),
            )
            if desc_el:
                description = desc_el.get_text(" ", strip=True)[:500]

        out.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "apply_url": apply_url,
            "source_url": url,
            "salary_min_usd": None,
            "salary_max_usd": None,
            "salary_source": None,
            "category": category,
        })

    return out
