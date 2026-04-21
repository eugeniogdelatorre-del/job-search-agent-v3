"""Rule-based 6-dim scorer with gates + weighted dimensions.

Architecture (see docs/ARCHITECTURE.md for full discussion):

    1. GATES — hard rejects from v2. A job that trips any gate gets score=0
       with the gate reason recorded. Not stored as null; null means "not yet
       scored" (pre-AI pipeline).
    2. DIMENSIONS — 6 weighted sub-scores, each 0-100:
         role_fit         (0.30)  title keyword match against PRIMARY/SECONDARY roles
         vertical_fit     (0.20)  category / vertical alignment
         channel_mix      (0.15)  source tier 3 > 2 > 1
         team_stage       (0.15)  heuristic signals in description
         geo_timezone     (0.10)  LATAM / Americas / Remote-open preference
         metrics_clarity  (0.10)  does the posting define what it wants
       Total = round(sum(dim_score * weight)) capped 0-100.

Config source of truth is the `scoring_config.config` jsonb row in Supabase,
merged on top of DEFAULT_CONFIG below. The /tune UI edits that jsonb.

Defaults below port Eugenio's v2 keyword sets (PRIMARY_ROLES, WEB3_KEYWORDS,
bilingual signals) 1:1 so first-scrape behavior matches v2 intent.
"""
from __future__ import annotations

import copy
import re
from typing import Any

# ---------------------------------------------------------------------------
# Default config (merged with DB scoring_config on load)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "gates": {
        "salary_floor_usd": 30000,
        "exclusions": [
            "intern", "internship", "unpaid", "volunteer",
            "senior sales", "outside sales", "door-to-door",
        ],
        "location_whitelist": [
            "remote", "worldwide", "global", "anywhere", "distributed",
            "work from home", "wfh", "all locations", "any location",
            "argentina", "buenos aires", "caba", "latam", "latin america",
            "south america", "americas",
            "brazil", "brasil", "colombia", "chile", "peru", "uruguay",
            "mexico", "costa rica", "ecuador",
        ],
        "onsite_blocked_cities": [
            "santiago", "lima", "bogota", "medellin", "sao paulo",
            "rio de janeiro", "quito", "montevideo", "san jose",
            "ciudad de mexico", "guadalajara", "dubai", "london",
            "new york", "san francisco", "tel aviv", "singapore",
            "hong kong", "belfast", "paris",
        ],
        "geo_restricted_markers": [
            "us only", "usa only", "u.s. only", "united states only",
            "us-based", "usa-based", "must be located in the us",
            "must reside in the us", "us residents only", "us citizens only",
            "uk only", "uk-based", "united kingdom only",
            "eu only", "eu-based", "europe only", "european union only",
            "canada only", "canada-based", "australia only",
            "apac only", "emea only",
            "authorized to work in the united states",
        ],
        "open_remote_markers": [
            "worldwide", "global", "anywhere", "latam", "latin america",
            "south america", "americas", "argentina", "buenos aires",
            "all locations", "any location", "any country",
        ],
    },
    "dimensions": {
        "role_fit": {
            "weight": 0.30,
            "primary_roles": [
                "community manager", "head of community", "community lead",
                "growth manager", "growth lead", "head of growth",
                "kol manager", "kol lead",
                "marketing manager", "marketing lead", "head of marketing",
                "social media manager", "content manager", "content lead",
                "partnerships manager", "partnership manager",
                "developer relations", "devrel",
            ],
            "secondary_roles": [
                "community", "growth", "marketing", "content", "partnerships",
                "ambassador", "evangelist", "advocate", "ecosystem",
            ],
            "title_penalties": [
                "engineer", "solidity", "rust developer", "backend developer",
                "smart contract", "senior full stack", "devops", "sre",
            ],
        },
        "vertical_fit": {
            "weight": 0.20,
            "boost_keywords": [
                "defi", "rwa", "oracle", "gaming", "cex", "dex",
                "layer 1", "layer 2", "l1", "l2", "stablecoin",
            ],
            "neutral_keywords": ["nft", "bridge", "forensics", "services"],
            "penalty_keywords": [],
        },
        "channel_mix": {
            "weight": 0.15,
            "tier_scores": {"3": 100, "2": 70, "1": 40, "0": 20},
        },
        "team_stage": {
            "weight": 0.15,
            "boost_signals": [
                "series b", "series c", "profitable", "revenue positive",
                "top 100", "top 50", "top 20", "backed by",
                "a16z", "paradigm", "sequoia", "pantera", "multicoin",
            ],
            "neutral_signals": ["series a", "growing", "funded"],
            "penalty_signals": ["pre-seed", "no funding", "bootstrapped"],
        },
        "geo_timezone": {
            "weight": 0.10,
            "boost_phrases": [
                "remote-first", "latam-friendly", "americas timezone",
                "latam", "latin america", "south america", "argentina",
            ],
            "neutral_phrases": ["global", "flexible", "worldwide"],
            "penalty_phrases": ["on-site only", "asia-only", "europe-only"],
        },
        "metrics_clarity": {
            "weight": 0.10,
            "boost_signals": [
                "salary range", "compensation range",
                "team size", "reports to", "kpi", "okr",
                "responsibilities", "what you'll do",
            ],
            "penalty_signals": ["competitive salary", "attractive package"],
        },
    },
    "thresholds": {"hot": 80, "warm": 60, "cold": 40},
}


# ---------------------------------------------------------------------------
# Config loader (merge DB on top of defaults)
# ---------------------------------------------------------------------------

def resolve_config(db_config: dict | None) -> dict:
    """Deep-merge `db_config` over `DEFAULT_CONFIG`."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if not db_config:
        return merged
    return _deep_merge(merged, db_config)


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

_HOURLY = re.compile(r"\$?(\d+)\s*[-\u2013]?\s*\$?(\d*)\s*/\s*h(?:our|r)?", re.IGNORECASE)
_MONTHLY_RANGE = re.compile(
    r"(\d{3,5})\s*[-\u2013]\s*(\d{3,5})\s*(?:USD|usd)?\s*/?(?:mes\b|month|mo\b|monthly)",
    re.IGNORECASE,
)
_MONTHLY_SINGLE = re.compile(
    r"(\d{3,5})\s*(?:USD|usd)\s*/?\s*(?:mes\b|month|mo\b)", re.IGNORECASE
)


def _blob(job: dict) -> str:
    return " ".join(
        (job.get(k) or "") for k in ("title", "company", "description", "location")
    ).lower()


def check_gates(job: dict, config: dict) -> str | None:
    """Return a rejection reason string, or None if all gates pass."""
    g = config["gates"]
    title = (job.get("title") or "").lower()
    location = (job.get("location") or "").lower()
    blob = _blob(job)

    # Exclusions in title
    for exc in g["exclusions"]:
        if exc in title:
            return f"title-excluded: {exc}"

    # Location whitelist: pass if empty OR matches any whitelist token.
    loc_ok = (
        not location
        or location in ("", "remote", "unknown")
        or any(w in location for w in g["location_whitelist"])
    )
    if not loc_ok:
        return f"location-not-accessible: {location[:60]}"

    # Onsite city blocks (unless Buenos Aires)
    is_onsite = any(
        kw in blob for kw in ("onsite", "on-site", "in-office", "presencial")
    )
    if is_onsite and not any(ba in blob for ba in ("buenos aires", "argentina", "caba")):
        for city in g["onsite_blocked_cities"]:
            if city in location or city in title:
                return f"onsite-blocked-city: {city}"

    # Geo-restricted remote (US-only, EU-only, etc.)
    is_open = any(m in blob for m in g["open_remote_markers"])
    is_restricted = any(m in blob for m in g["geo_restricted_markers"])
    if is_restricted and not is_open:
        return "geo-restricted-remote"

    # Salary floor gates (listed salary OR description hourly / monthly sniff)
    floor = int(g.get("salary_floor_usd") or 0)
    if floor > 0:
        sal_max = job.get("salary_max_usd")
        if isinstance(sal_max, int) and sal_max > 0 and sal_max < floor:
            return f"below-floor-listed: {sal_max}"
        m = _MONTHLY_RANGE.search(blob)
        if m and int(m.group(2)) * 12 < floor:
            return f"below-floor-monthly: {m.group(2)}/mo"
        m = _MONTHLY_SINGLE.search(blob)
        if m and int(m.group(1)) * 12 < floor:
            return f"below-floor-monthly: {m.group(1)}/mo"
        m = _HOURLY.search(blob)
        if m:
            low = int(m.group(1))
            if 1 < low < 100 and low * 40 * 52 < floor:
                return f"below-floor-hourly: {low}/hr"

    return None


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def _dim_role_fit(job: dict, cfg: dict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    title = (job.get("title") or "").lower()
    score = 0
    for role in cfg["primary_roles"]:
        if role in title:
            score = 100
            reasons.append(f"primary: {role}")
            break
    if score == 0:
        for role in cfg["secondary_roles"]:
            if role in title:
                score = 60
                reasons.append(f"secondary: {role}")
                break
    for pen in cfg["title_penalties"]:
        if pen in title:
            score = max(0, score - 30)
            reasons.append(f"-penalty: {pen}")
    return (max(0, min(100, score)), reasons)


def _dim_vertical_fit(job: dict, cfg: dict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    blob = _blob(job)
    score = 50  # neutral baseline
    boost_hits = sum(1 for kw in cfg["boost_keywords"] if kw in blob)
    if boost_hits:
        score = min(100, 60 + boost_hits * 10)
        reasons.append(f"+boost x{boost_hits}")
    for kw in cfg.get("penalty_keywords", []):
        if kw in blob:
            score = max(0, score - 20)
            reasons.append(f"-penalty: {kw}")
    return (score, reasons)


def _dim_channel_mix(job: dict, cfg: dict) -> tuple[int, list[str]]:
    tier = str(job.get("source_tier") or 0)
    score = int(cfg["tier_scores"].get(tier, 20))
    return (score, [f"tier={tier}"])


def _dim_team_stage(job: dict, cfg: dict) -> tuple[int, list[str]]:
    blob = _blob(job)
    reasons: list[str] = []
    score = 50  # unknown = neutral
    for sig in cfg["boost_signals"]:
        if sig in blob:
            score = min(100, score + 20)
            reasons.append(f"+{sig}")
    for sig in cfg.get("neutral_signals", []):
        if sig in blob:
            score = min(100, score + 5)
    for sig in cfg.get("penalty_signals", []):
        if sig in blob:
            score = max(0, score - 20)
            reasons.append(f"-{sig}")
    return (score, reasons)


def _dim_geo_timezone(job: dict, cfg: dict) -> tuple[int, list[str]]:
    blob = _blob(job)
    reasons: list[str] = []
    score = 50
    for p in cfg["boost_phrases"]:
        if p in blob:
            score = min(100, score + 15)
            reasons.append(f"+{p}")
            break
    for p in cfg.get("penalty_phrases", []):
        if p in blob:
            score = max(0, score - 25)
            reasons.append(f"-{p}")
    return (score, reasons)


def _dim_metrics_clarity(job: dict, cfg: dict) -> tuple[int, list[str]]:
    blob = _blob(job)
    reasons: list[str] = []
    score = 30  # unclear baseline: most listings are vague
    for sig in cfg["boost_signals"]:
        if sig in blob:
            score = min(100, score + 15)
            reasons.append(f"+{sig}")
    for sig in cfg.get("penalty_signals", []):
        if sig in blob:
            score = max(0, score - 10)
            reasons.append(f"-{sig}")
    # Having salary fields extracted by the parser is itself a clarity signal
    if job.get("salary_min_usd") and job.get("salary_max_usd"):
        score = min(100, score + 20)
        reasons.append("+salary listed")
    return (score, reasons)


DIM_FUNCS = {
    "role_fit": _dim_role_fit,
    "vertical_fit": _dim_vertical_fit,
    "channel_mix": _dim_channel_mix,
    "team_stage": _dim_team_stage,
    "geo_timezone": _dim_geo_timezone,
    "metrics_clarity": _dim_metrics_clarity,
}


def score_job(job: dict, config: dict | None = None) -> tuple[int, dict]:
    """Return (total_0_100, breakdown dict).

    breakdown shape:
        {
          "gate_failed": "<reason>" | None,
          "dimensions": {
             "role_fit":    {"score": 0-100, "weight": 0.30, "reasons": [..]},
             ...
          },
          "total": 0-100,
        }
    """
    cfg = config if config is not None else DEFAULT_CONFIG
    gate_reason = check_gates(job, cfg)
    breakdown: dict[str, Any] = {
        "gate_failed": gate_reason,
        "dimensions": {},
        "total": 0,
    }

    if gate_reason is not None:
        return (0, breakdown)

    weighted_total = 0.0
    for name, func in DIM_FUNCS.items():
        dim_cfg = cfg["dimensions"][name]
        sub_score, reasons = func(job, dim_cfg)
        weight = float(dim_cfg["weight"])
        weighted_total += sub_score * weight
        breakdown["dimensions"][name] = {
            "score": sub_score,
            "weight": weight,
            "reasons": reasons,
        }

    total = max(0, min(100, round(weighted_total)))
    breakdown["total"] = total
    return (total, breakdown)
