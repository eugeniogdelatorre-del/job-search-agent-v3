"""Probe the 51 benchmark Web3 companies that aren't in sources.json yet
against the four common ATS endpoints (Greenhouse, Lever, Ashby, Workable).

For each company we try a handful of plausible slug variants on each ATS
and accept the first that returns a non-empty job board. Output is a JSON
file ready to be merged into ``scraper/sources.json``.

Usage:
    python scripts/probe_missing_sources.py [--out FILE]

Writes ``probe_results.json`` (or whatever --out points at) with shape:
    {
      "verified": [
        {"name": "Compound", "url": "https://boards.greenhouse.io/compound",
         "category": "DeFi", "ats": "greenhouse", "job_count": 4},
        ...
      ],
      "rejected": [
        {"name": "Frame", "reason": "no public board on any ATS"},
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

# Companies to probe + a hint of what category they'd land in. The
# category mirrors values used in existing sources.json entries; the
# scoring config treats unknown categories as neutral so this is just
# UI/grouping metadata.
TARGETS: list[tuple[str, str]] = [
    # CEX / custody / stablecoin
    ("Bitstamp",          "CEX"),
    ("MEXC",              "CEX"),
    ("Anchorage",         "Custody"),
    ("MakerDAO",          "DeFi"),
    ("Sky",               "DeFi"),
    ("Mountain Protocol", "Stablecoin"),
    ("Ondo",              "Stablecoin"),
    # DeFi protocols
    ("Compound",          "DeFi"),
    ("Curve",             "DeFi"),
    ("Frax",              "DeFi"),
    ("Yearn",             "DeFi"),
    ("Pendle",            "DeFi"),
    ("GMX",               "DeFi"),
    ("dYdX",              "DeFi"),
    # Cross-chain / DA / restaking
    ("Across",            "Bridge"),
    ("deBridge",          "Bridge"),
    ("Avail",             "DA"),
    ("EigenLayer",        "Restaking"),
    ("Polymer",           "Bridge"),
    ("Symbiotic",         "Restaking"),
    ("Karak",             "Restaking"),
    ("Renzo",             "Restaking"),
    ("EtherFi",           "Restaking"),
    ("Kelp",              "Restaking"),
    ("Puffer",            "Restaking"),
    ("Babylon",           "Restaking"),
    # Wallets / tooling
    ("Rabby",             "Wallet"),
    ("Frame",              "Wallet"),
    ("Tenderly",          "Infra"),
    ("Infura",            "Infra"),
    ("Chainstack",        "Infra"),
    ("Crossmint",         "Infra"),
    ("Privy",             "Infra"),
    ("Magic",             "Infra"),
    ("Foundry",           "Tools"),
    ("Snapshot",          "Tools"),
    ("Safe",              "Wallet"),
    # L2s / new chains
    ("Linea",             "L2"),
    ("Base",              "L2"),
    ("Manta",             "L2"),
    ("Mode",              "L2"),
    ("Blast",             "L2"),
    ("Sei",               "L1"),
    ("Movement",          "L1"),
    ("Initia",            "L1"),
    ("Fuel",              "L2"),
    # Oracles / data
    ("Pyth",              "Oracle"),
    ("RedStone",          "Oracle"),
    ("API3",              "Oracle"),
    # Privacy
    ("Aleo",              "Privacy"),
    ("Mina",              "Privacy"),
]


def _slug_variants(name: str) -> list[str]:
    """Plausible slugs to probe per company. Ordered by likelihood —
    we stop at the first hit per ATS so cheap variants first.
    """
    base = name.lower().strip()
    # Strip punctuation and common stop-strings.
    base = re.sub(r"[.\s]+", "-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    variants = [base]
    # Common suffixes companies add to slugs.
    for suffix in ("-labs", "labs", "-foundation", "foundation", "-network",
                   "network", "-finance", "finance", "-protocol", "protocol",
                   "-xyz", "-io", "-inc"):
        candidate = base + suffix.replace("-", "")
        if candidate != base:
            variants.append(candidate)
        if suffix.startswith("-"):
            variants.append(base + suffix)
    # No-hyphen variant (e.g. "etherfi" instead of "ether-fi")
    variants.append(base.replace("-", ""))
    # Deduplicate, preserve order
    seen = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
    })
    return s


TIMEOUT = 10  # per request

# ─── Greenhouse ──────────────────────────────────────────────────────────────

def probe_greenhouse(s: requests.Session, slug: str) -> int | None:
    """Returns job_count if board exists and has jobs (or zero), else None."""
    try:
        r = s.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=TIMEOUT)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json() or {}
    except ValueError:
        return None
    jobs = data.get("jobs")
    return len(jobs) if isinstance(jobs, list) else None


# ─── Lever ────────────────────────────────────────────────────────────────────

def probe_lever(s: requests.Session, slug: str) -> int | None:
    try:
        r = s.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=TIMEOUT)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if isinstance(data, list):
        return len(data)
    return None


# ─── Ashby ────────────────────────────────────────────────────────────────────

def probe_ashby(s: requests.Session, slug: str) -> int | None:
    try:
        r = s.get(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
            timeout=TIMEOUT,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    body = (r.text or "").strip()
    if not body:
        return None
    try:
        data = r.json() or {}
    except ValueError:
        return None
    jobs = data.get("jobs")
    return len(jobs) if isinstance(jobs, list) else None


# ─── Workable ────────────────────────────────────────────────────────────────

def probe_workable(s: requests.Session, slug: str) -> int | None:
    try:
        r = s.get(
            f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
            timeout=TIMEOUT,
        )
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json() or {}
    except ValueError:
        return None
    jobs = data.get("jobs")
    return len(jobs) if isinstance(jobs, list) else None


ATS_PROBES = [
    ("greenhouse", "https://boards.greenhouse.io/{slug}",   probe_greenhouse),
    ("lever",      "https://jobs.lever.co/{slug}",          probe_lever),
    ("ashby",      "https://jobs.ashbyhq.com/{slug}",        probe_ashby),
    ("workable",   "https://apply.workable.com/{slug}",     probe_workable),
]


def probe(name: str, category: str, session: requests.Session) -> dict | None:
    """Try every (ats, slug-variant) combo. Return the first hit, or None."""
    for slug in _slug_variants(name):
        for ats, url_tmpl, fn in ATS_PROBES:
            jobs = fn(session, slug)
            if jobs is None:
                continue
            # Accept boards with zero current jobs too — the company has
            # a public board, just isn't hiring right now. Future scrapes
            # will pick up new postings.
            return {
                "name": name,
                "url": url_tmpl.format(slug=slug),
                "category": category,
                "ats": ats,
                "job_count": jobs,
            }
            # (no need to break the inner loop — we already returned)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probe_results.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    s = _make_session()
    verified: list[dict] = []
    rejected: list[dict] = []

    for i, (name, category) in enumerate(TARGETS):
        if not args.quiet:
            print(f"  [{i+1}/{len(TARGETS)}] {name:<25s} ", end="", flush=True)
        hit = probe(name, category, s)
        if hit:
            verified.append(hit)
            if not args.quiet:
                print(f"-> {hit['ats']:<10s} {hit['url']:<60s}  jobs={hit['job_count']}")
        else:
            rejected.append({"name": name, "reason": "no public board on any ATS"})
            if not args.quiet:
                print("-> SKIP")
        # Be polite — don't hammer the ATS.
        time.sleep(0.4)

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps({"verified": verified, "rejected": rejected}, indent=2),
        encoding="utf-8",
    )
    print()
    print(f"  Wrote {out_path}: {len(verified)} verified, {len(rejected)} rejected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
