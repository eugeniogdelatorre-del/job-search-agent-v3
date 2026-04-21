"""Junk filters + aggregator title unmasher.

Ported from v2 `scraper/migrate_to_supabase.py` with the same rule set.
Applied in `scrape.py` after parsers run but before scoring.

Three concerns:
  1. X / Twitter feed sources are hiring-signals, not job listings. Dropped
     wholesale at source-load time in `sources.py` and here as a safety net.
  2. Aggregator sidebars get scraped as if they were jobs (e.g. "Promoted",
     "Find flexible remote roles"). Dropped by marker-list match on title.
  3. WeWorkRemotely and similar aggregators mash title+age+company+type+
     location+salary into a single string. Unmashed back into real fields.
"""
from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# X/Twitter feed detection (defence in depth — also filtered at load time)
# ---------------------------------------------------------------------------

def is_x_feed_source(source: dict) -> bool:
    if source.get("category") == "X_Feed":
        return True
    name = (source.get("name") or "").lower()
    return name.startswith("x: @") or name.startswith("x:@")


# ---------------------------------------------------------------------------
# Sidebar-ad / promo-row junk markers
# ---------------------------------------------------------------------------
# Markers that reliably identify sidebar/promotional content on aggregator
# sites scraped as if they were jobs. Conservative — only drops rows where
# the title is suspiciously long AND contains one of these markers.

JUNK_MARKERS = (
    "promoted",
    "curated marches",
    "find flexible remote roles",
    "curated by",
    "hiring talent from",
    "browse jobs",
    "post a job",
    "see all jobs",
    "view all openings",
    "featured jobs",
    "top remote companies",
)


def is_junk_listing(job: dict) -> bool:
    title = (job.get("title") or "").lower()
    if len(title) < 80:
        return False  # only very long suspicious titles get flagged
    return any(marker in title for marker in JUNK_MARKERS)


# ---------------------------------------------------------------------------
# Aggregator title unmasher (WWR-style)
# ---------------------------------------------------------------------------
# WeWorkRemotely concatenates HTML elements without separators:
#   "<title><age><company><type><location><salary?>" all jammed into one string.
# We reverse-engineer the original fields.

AGGREGATOR_COMPANIES = {
    "cryptojobslist", "web3.career", "cryptocurrencyjobs",
    "we work remotely", "remoteleaf", "remotive",
}

WWR_SPLIT = re.compile(
    r"^(?P<title>.+?)"                                         # real job title
    r"(?P<age>\d+[dmhw]|\d+mo|Featured|Top\s*\d+)"            # age/badge token
    r"(?P<company>.+?)"                                        # company + maybe location
    r"(?P<emp>Full-Time|Part-Time|Contract|Freelance|Internship)"
    r"(?P<tail>.*)$"                                           # location + maybe salary
)


def _split_company_location(s: str) -> tuple[str, str | None]:
    """Split 'VantaSan Francisco' -> ('Vanta', 'San Francisco')."""
    s = re.sub(r"(Featured|Top\s*\d+)+$", "", s).strip()
    m = re.search(r"([a-z])([A-Z])", s)
    if m:
        return (s[: m.start() + 1].strip(), s[m.start() + 1 :].strip())
    return (s, None)


def _split_location_salary(s: str) -> tuple[str, tuple[int, int] | None]:
    """Pull a USD salary range out of the location tail if present."""
    # Pattern A: "$10,000 - $25,000 USD"
    m = re.search(r"\$?([\d,]+)\s*[-–]\s*\$?([\d,]+)\s*USD", s)
    if m:
        lo = int(m.group(1).replace(",", ""))
        hi = int(m.group(2).replace(",", ""))
        loc = re.sub(r"\$?[\d,]+\s*[-–]\s*\$?[\d,]+\s*USD\s*", "", s).strip() or "Anywhere in the World"
        if 10_000 <= lo <= hi <= 1_000_000:
            return (loc, (lo, hi))
    # Pattern B: "$100,000 or more USD"
    m = re.search(r"\$([\d,]+)\s*or\s*more\s*USD?", s)
    if m:
        lo = int(m.group(1).replace(",", ""))
        loc = re.sub(r"\$[\d,]+\s*or\s*more\s*USD?\s*", "", s).strip() or "Anywhere in the World"
        if 10_000 <= lo <= 1_000_000:
            return (loc, (lo, lo))
    return (s, None)


def unmash_aggregator_title(job: dict) -> dict:
    """Extract real fields from mashed aggregator titles. No-op on failure.

    Returns a modified copy of the job dict. Preserves the aggregator name
    in `_discovery_channel` so downstream knows which source found the job.
    """
    title_raw = job.get("title") or ""
    if len(title_raw) < 80:
        return job
    m = WWR_SPLIT.match(title_raw)
    if not m:
        return job

    real_title = m.group("title").strip()
    company_raw = m.group("company").strip()
    tail = m.group("tail").strip()

    real_company, bled_location = _split_company_location(company_raw)
    location_clean, salary_range = _split_location_salary(tail)

    if bled_location and (not location_clean or location_clean == "Anywhere in the World"):
        location_clean = bled_location

    out = dict(job)
    original_company = (job.get("company") or "").lower()
    if original_company in AGGREGATOR_COMPANIES and real_company:
        out["_discovery_channel"] = job["company"]
        out["company"] = real_company
    out["title"] = real_title
    if location_clean:
        out["location"] = location_clean
    if salary_range and not out.get("salary_min_usd"):
        out["salary_min_usd"] = salary_range[0]
        out["salary_max_usd"] = salary_range[1]
        out["salary_source"] = "listed"
    return out


def clean_jobs(jobs: list[dict]) -> tuple[list[dict], dict]:
    """Apply all cleanup passes. Returns (cleaned_jobs, stats)."""
    stats = {"junk_dropped": 0, "unmashed": 0}
    out = []
    for job in jobs:
        if is_junk_listing(job):
            stats["junk_dropped"] += 1
            continue
        cleaned = unmash_aggregator_title(job)
        if cleaned is not job:
            stats["unmashed"] += 1
        out.append(cleaned)
    return out, stats
