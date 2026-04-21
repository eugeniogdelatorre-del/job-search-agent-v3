"""WeWorkRemotely parser.

Category-specific RSS feeds (e.g. `remote-blockchain-jobs.rss`) are behind
a Cloudflare challenge as of 2026. Workaround: hit the main feed at
`/remote-jobs.rss` and filter client-side by Web3 keywords on
title + category + skills + description.

RSS fields we care about per <item>:
    title, link, pubDate, description, category, type, region, country, skills
WWR formats the title as "{Company}: {Job Title}".
"""
from __future__ import annotations

import html
import re
from xml.etree import ElementTree as ET

import requests

from .base import REQUEST_TIMEOUT_SECONDS

name = "weworkremotely"

WWR_HOST = "weworkremotely.com"
WWR_FEED = "https://weworkremotely.com/remote-jobs.rss"

WEB3_KEYWORDS = re.compile(
    r"\b(blockchain|crypto|web3|defi|dao|nft|token|ethereum|solana|bitcoin|"
    r"l2|layer[\s\-]?2|evm|smart[\s\-]?contract|stablecoin|on[\s\-]?chain|"
    r"rollup|zk|zero[\s\-]?knowledge|dex|cefi|wallet|polkadot|cosmos|"
    r"metaverse|gamefi|depin|rwa)\b",
    re.IGNORECASE,
)


def can_parse(source: dict) -> bool:
    return WWR_HOST in (source.get("url") or "").lower()


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    txt = html.unescape(raw)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _is_web3_relevant(item_text: str) -> bool:
    return bool(WEB3_KEYWORDS.search(item_text))


def _split_title(mashed: str) -> tuple[str, str | None]:
    """WWR titles are '{Company}: {Job Title}'. Falls back to (whole, None)."""
    if ":" in mashed:
        company, _, job_title = mashed.partition(":")
        return job_title.strip(), company.strip()
    return mashed.strip(), None


def parse(session: requests.Session, source: dict) -> list[dict]:
    resp = session.get(WWR_FEED, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"WWR RSS {resp.status_code}")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        raise RuntimeError(f"WWR RSS parse error: {e}")

    channel = root.find("channel")
    if channel is None:
        return []

    category = source.get("category") or "Remote_Board"
    out: list[dict] = []

    for item in channel.findall("item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description_raw = item.findtext("description") or ""
        cat = (item.findtext("category") or "").strip()
        job_type = (item.findtext("type") or "").strip()
        region = (item.findtext("region") or "").strip()
        country = (item.findtext("country") or "").strip()
        skills = (item.findtext("skills") or "").strip()

        if not title_raw or not link:
            continue

        # Keyword-filter the noisy feed for Web3 relevance.
        haystack = " ".join([title_raw, cat, skills, description_raw[:2000]])
        if not _is_web3_relevant(haystack):
            continue

        job_title, company = _split_title(title_raw)
        location = region or country or "Remote"
        description = _strip_html(description_raw)[:5000]

        out.append({
            "title": job_title,
            "company": company or "We Work Remotely",
            "location": location,
            "description": description or None,
            "apply_url": link,
            "source_url": source.get("url"),
            "salary_min_usd": None,
            "salary_max_usd": None,
            "salary_source": None,
            "category": category,
            "_job_type": job_type or None,
        })

    return out
