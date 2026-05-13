"""For each company without a public ATS slug, fetch their main careers
page and detect which ATS is embedded.

Many Web3 companies use bespoke careers pages that iframe in or link
out to a hosted ATS (Greenhouse / Lever / Ashby / Workable / Notion).
This script probes ``{company}.com/careers``, ``/jobs``, ``/join`` and
``careers.{company}.com`` for each name and looks for ATS-specific URL
patterns in the response body. Output is a hint list — the operator
manually verifies + adds the right ones to sources.json.

Usage:
    python scripts/detect_ats_from_careers.py [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


# The 29 companies that probe_missing_sources.py couldn't match against
# the four standard ATS endpoints. The second element is a best-guess
# canonical domain — if a company has multiple (e.g. .com + .xyz), we
# try the most well-known.
TARGETS: list[tuple[str, str]] = [
    ("MEXC",              "mexc.com"),
    ("Mountain Protocol", "mountainprotocol.com"),
    ("Ondo",              "ondo.finance"),
    ("Frax",              "frax.finance"),
    ("Yearn",             "yearn.fi"),
    ("Pendle",            "pendle.finance"),
    ("GMX",               "gmx.io"),
    ("dYdX",              "dydx.foundation"),
    ("Across",            "across.to"),
    ("deBridge",          "debridge.finance"),
    ("Avail",             "availproject.org"),
    ("EigenLayer",        "eigenlayer.xyz"),
    ("Polymer",           "polymerlabs.org"),
    ("Karak",             "karak.network"),
    ("Renzo",             "renzoprotocol.com"),
    ("EtherFi",           "ether.fi"),
    ("Kelp",              "kelpdao.xyz"),
    ("Puffer",            "puffer.fi"),
    ("Rabby",             "rabby.io"),
    ("Tenderly",          "tenderly.co"),
    ("Infura",            "infura.io"),
    ("Chainstack",        "chainstack.com"),
    ("Crossmint",         "crossmint.com"),
    ("Privy",             "privy.io"),
    ("Snapshot",          "snapshot.org"),
    ("Initia",            "initia.xyz"),
    ("RedStone",          "redstone.finance"),
    ("API3",              "api3.org"),
    ("Aleo",              "aleo.org"),
]


# ATS signatures: substrings or regex patterns that, if present in the
# careers page HTML, strongly imply the company is using that ATS.
ATS_SIGNATURES: list[tuple[str, re.Pattern]] = [
    # Greenhouse — embed iframe + boards-api URL
    ("greenhouse", re.compile(r"boards\.greenhouse\.io/(?:embed/)?[a-z0-9_-]+|boards-api\.greenhouse\.io|job-board\.greenhouse\.io/[a-z0-9_-]+", re.I)),
    # Lever — postings api or jobs.lever.co
    ("lever",      re.compile(r"jobs\.lever\.co/[a-z0-9_-]+|api\.lever\.co/v0/postings/[a-z0-9_-]+", re.I)),
    # Ashby
    ("ashby",      re.compile(r"jobs\.ashbyhq\.com/[a-z0-9_-]+|api\.ashbyhq\.com/posting-api", re.I)),
    # Workable
    ("workable",   re.compile(r"apply\.workable\.com/[a-z0-9_-]+", re.I)),
    # Workday — public board hostnames
    ("workday",    re.compile(r"[a-z0-9_-]+\.wd[0-9]+\.myworkdayjobs\.com", re.I)),
    # BambooHR
    ("bamboohr",   re.compile(r"[a-z0-9_-]+\.bamboohr\.com/careers", re.I)),
    # Teamtailor
    ("teamtailor", re.compile(r"[a-z0-9_-]+\.teamtailor\.com", re.I)),
    # SmartRecruiters
    ("smartrecruiters", re.compile(r"smartrecruiters\.com/[A-Za-z0-9_-]+", re.I)),
    # JazzHR
    ("jazzhr",     re.compile(r"[a-z0-9_-]+\.applytojob\.com", re.I)),
    # Recruitee
    ("recruitee",  re.compile(r"[a-z0-9_-]+\.recruitee\.com", re.I)),
    # Personio (legacy)
    ("personio",   re.compile(r"[a-z0-9_-]+\.jobs\.personio\.(?:com|de)", re.I)),
    # Notion (no scraping — but worth flagging)
    ("notion",     re.compile(r"notion\.site/[a-z0-9-]+|[a-z0-9_-]+\.notion\.site", re.I)),
    # Pinpoint
    ("pinpoint",   re.compile(r"app\.pinpointhq\.com|[a-z0-9_-]+\.pinpointhq\.com", re.I)),
    # Breezy
    ("breezy",     re.compile(r"[a-z0-9_-]+\.breezy\.hr", re.I)),
    # Wellfound / AngelList Talent
    ("wellfound",  re.compile(r"wellfound\.com/jobs|angel\.co/", re.I)),
]


PATHS = ["/careers", "/jobs", "/join", "/team", "/hiring", "/work-with-us", "/"]
CAREERS_SUBDOMAINS = ["careers", "jobs", "join", "work"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIMEOUT = 10


def detect_in_text(text: str) -> list[tuple[str, str]]:
    """Return list of (ats_name, matched_substring) hits."""
    out: list[tuple[str, str]] = []
    for ats, pat in ATS_SIGNATURES:
        m = pat.search(text)
        if m:
            out.append((ats, m.group(0)))
    return out


def probe_company(session: requests.Session, name: str, domain: str) -> dict:
    """Try several URL variants for one company. Return summary."""
    urls_to_try = []
    for path in PATHS:
        urls_to_try.append(f"https://{domain}{path}")
    for sub in CAREERS_SUBDOMAINS:
        urls_to_try.append(f"https://{sub}.{domain}/")

    seen_signatures: dict[str, list[str]] = {}
    fetched_ok = False
    last_error = None

    for url in urls_to_try:
        try:
            r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:
            last_error = str(e)
            continue
        if r.status_code >= 400:
            continue
        fetched_ok = True
        hits = detect_in_text(r.text)
        for ats, sample in hits:
            seen_signatures.setdefault(ats, []).append(f"{url} -> {sample[:80]}")

    return {
        "name": name,
        "domain": domain,
        "fetched_ok": fetched_ok,
        "ats_hits": seen_signatures,
        "last_error": last_error,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ats_detection_results.json")
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update(HEADERS)

    results = []
    for i, (name, domain) in enumerate(TARGETS):
        print(f"  [{i+1}/{len(TARGETS)}] {name:<20s} {domain:<30s}", end=" ", flush=True)
        r = probe_company(s, name, domain)
        results.append(r)
        if r["ats_hits"]:
            atses = list(r["ats_hits"].keys())
            print(f"-> {','.join(atses)}")
        elif r["fetched_ok"]:
            print("-> reachable but no ATS detected (likely custom / Notion / JS-only)")
        else:
            print(f"-> unreachable ({r.get('last_error') or 'all 4xx'})")
        time.sleep(0.3)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")

    # Quick action list
    print("\nACTIONABLE HITS (a real ATS slug found in the page):")
    for r in results:
        for ats, samples in r["ats_hits"].items():
            if ats in ("notion", "wellfound"):
                continue  # not scrapable cleanly
            print(f"  - {r['name']:<20s} {ats:<15s} {samples[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
