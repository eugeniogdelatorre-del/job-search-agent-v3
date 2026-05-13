"""Rule-based 6-dim scorer with gates + weighted dimensions.

Location filtering is no longer done here — geo_filter.py (Phase 2.5) owns
that responsibility now. Gates left in place: title exclusions + salary floor.

    1. GATES — hard rejects. A job that trips any gate gets score=0 with the
       gate reason recorded. Null means "not yet scored" (pre-AI pipeline).
    2. DIMENSIONS — 6 weighted sub-scores, each 0-100:
         role_fit         (0.30)  title keyword match against PRIMARY/SECONDARY roles
         vertical_fit     (0.20)  category / vertical alignment
         channel_mix      (0.15)  source tier 3 > 2 > 1
         team_stage       (0.15)  heuristic signals in description
         geo_timezone     (0.10)  LATAM / Americas / Remote-open preference
         metrics_clarity  (0.10)  does the posting define what it wants
       Total = round(sum(dim_score * weight)) capped 0-100.

Config is hard-coded in DEFAULT_CONFIG below. The /tune UI was removed once
cv_score.py (AI scorer) became the primary ranker — rule-based score_total
now serves only as a budget gate (cv_score skips rows with score_total < 40).
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Default config — single source of truth (no DB merge)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "gates": {
        # NOTE: salary_floor_usd was removed on 2026-05-13. Salary is now
        # a SOFT signal handled by ``_salary_band_penalty()`` (band
        # [SALARY_BAND_MIN_USD, SALARY_BAND_MAX_USD] = $30k-$120k, -5
        # outside) rather than a hard reject. Edit those constants
        # below if you want to tune the band; the config dict no longer
        # carries a salary field.
        "exclusions": [
            "intern", "internship", "unpaid", "volunteer",
            "senior sales", "outside sales", "door-to-door",
        ],
    },
    "dimensions": {
        "role_fit": {
            "weight": 0.30,
            # Expanded 2026-05-13 (audit V-1): Web3 community/growth/brand
            # titles are creative ("Head of Belonging", "Discord Lead",
            # "Ecosystem Catalyst", "Brand Strategist"). Adding the common
            # variants lifts more roles above the rule-score floor so
            # they reach AI evaluation.
            "primary_roles": [
                # Community
                "community manager", "head of community", "community lead",
                "discord manager", "discord lead", "community operations",
                "community ops", "community strategy",
                # Growth
                "growth manager", "growth lead", "head of growth",
                "growth marketing", "growth strategy", "growth operations",
                "user acquisition",
                # Marketing / brand
                "marketing manager", "marketing lead", "head of marketing",
                "brand manager", "brand lead", "head of brand",
                "brand strategy",
                # Social / content / KOL
                "social media manager", "content manager", "content lead",
                "head of content", "content strategy",
                "kol manager", "kol lead",
                # Partnerships / BD / ecosystem
                "partnerships manager", "partnership manager",
                "ecosystem manager", "ecosystem lead", "head of ecosystem",
                "business development manager", "bd manager", "bd lead",
                # DevRel-adjacent
                "developer relations", "devrel",
                "developer advocate", "developer experience",
                "developer marketing", "head of devrel",
                # Leadership (small co's wear hats)
                "chief of staff",
            ],
            "secondary_roles": [
                # Original
                "community", "growth", "marketing", "content", "partnerships",
                "ambassador", "evangelist", "advocate", "ecosystem",
                # Expansion
                "discord", "moderator", "moderation",
                "acquisition", "retention", "activation",
                "brand", "creative", "editorial", "copywriter",
                "bizdev", "biz dev",
                "advocacy", "evangelism",
                "operations",
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
            # 2026-05-13 (audit H-6): "bootstrapped" moved from penalty to
            # neutral. Profitable bootstrapped Web3 companies are often
            # a STRONG fit for community/growth/marketing roles (smaller
            # team, more impact per hire) — penalizing them was
            # dropping good leads below the warm threshold.
            "neutral_signals": ["series a", "growing", "funded", "bootstrapped"],
            "penalty_signals": ["pre-seed", "no funding"],
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
# Gates
# ---------------------------------------------------------------------------

# Audit M17: anchor the period words with \b on BOTH sides. Without
# leading-boundary, ``mo`` and ``month`` matched inside ``mode``, ``money``,
# ``smooth``, etc. \u2014 false positives that gated legitimate jobs as
# "below-floor-monthly". Same for ``mes`` and ``monthly``. The lookahead
# at the end ensures the period word is followed by a non-word char or
# end-of-string so ``monthsworking`` doesn't accidentally re-match.
_PERIOD_MONTH = r"\b(?:mes|month|mo|monthly)\b"
_PERIOD_HOUR = r"\b(?:hour|hr|h)\b"
_HOURLY = re.compile(
    rf"\$?(\d+)\s*[-\u2013]?\s*\$?(\d*)\s*/\s*{_PERIOD_HOUR}",
    re.IGNORECASE,
)
_MONTHLY_RANGE = re.compile(
    rf"(\d{{3,5}})\s*[-\u2013]\s*(\d{{3,5}})\s*(?:USD|usd)?\s*/?\s*{_PERIOD_MONTH}",
    re.IGNORECASE,
)
_MONTHLY_SINGLE = re.compile(
    rf"(\d{{3,5}})\s*(?:USD|usd)\s*/?\s*{_PERIOD_MONTH}", re.IGNORECASE
)


def _blob(job: dict) -> str:
    return " ".join(
        (job.get(k) or "") for k in ("title", "company", "description", "location")
    ).lower()


# Audit 2026-05-13: salary is no longer a hard gate. Out-of-band salaries
# now apply a small penalty via _salary_band_penalty() so the role is
# still surfaced (sorted lower) instead of vanishing. Edit these bands
# in one place; the gates and the penalty share them.
SALARY_BAND_MIN_USD = 30_000
SALARY_BAND_MAX_USD = 120_000
SALARY_BAND_PENALTY = 5


def check_gates(job: dict, config: dict) -> str | None:
    """Return a rejection reason string, or None if all gates pass.

    Salary is intentionally NOT gated here anymore — see
    ``_salary_band_penalty()`` for the soft-signal version. The title
    exclusion list is the only remaining hard gate.
    """
    g = config["gates"]
    title = (job.get("title") or "").lower()

    # Exclusions in title
    for exc in g["exclusions"]:
        if exc in title:
            return f"title-excluded: {exc}"

    return None


def _detect_annual_salary_from_blob(blob: str) -> tuple[int | None, int | None]:
    """Infer (low, high) annual USD from monthly/hourly mentions in the
    description. Returns (None, None) if nothing matches. The caller's
    listed salary_min/max_usd takes precedence over this inference.
    """
    m = _MONTHLY_RANGE.search(blob)
    if m:
        return (int(m.group(1)) * 12, int(m.group(2)) * 12)
    m = _MONTHLY_SINGLE.search(blob)
    if m:
        v = int(m.group(1)) * 12
        return (v, v)
    m = _HOURLY.search(blob)
    if m:
        low = int(m.group(1))
        if 1 < low < 100:
            v = low * 40 * 52
            return (v, v)
    return (None, None)


def _salary_band_penalty(job: dict) -> tuple[int, str | None]:
    """Soft penalty when the salary range falls entirely outside the
    target band [SALARY_BAND_MIN_USD, SALARY_BAND_MAX_USD]. Returns
    (penalty <= 0, reason or None).

    Listed salary on the job row wins. If unlisted, we sniff the
    description for monthly/hourly mentions. Missing salary altogether
    = neutral (no penalty), since most listings don't disclose.
    """
    listed_min = job.get("salary_min_usd")
    listed_max = job.get("salary_max_usd")
    lo: int | None = listed_min if isinstance(listed_min, int) and listed_min > 0 else None
    hi: int | None = listed_max if isinstance(listed_max, int) and listed_max > 0 else None

    if lo is None and hi is None:
        # Fall back to description sniff so a $20/hr internship still
        # gets penalized even when the parser didn't extract salary
        # fields directly.
        blob = _blob(job)
        lo, hi = _detect_annual_salary_from_blob(blob)

    if lo is None and hi is None:
        return (0, None)

    # Treat a single-sided range as a point (e.g. "$150k+" → lo=150k,
    # hi=None). For the band check, look at whichever side is known.
    effective_high = hi if hi is not None else lo
    effective_low = lo if lo is not None else hi

    # Whole range BELOW band: max is under the band's lower bound.
    if effective_high is not None and effective_high < SALARY_BAND_MIN_USD:
        return (-SALARY_BAND_PENALTY,
                f"-{SALARY_BAND_PENALTY} below-band: max={effective_high}")
    # Whole range ABOVE band: min is over the band's upper bound.
    if effective_low is not None and effective_low > SALARY_BAND_MAX_USD:
        return (-SALARY_BAND_PENALTY,
                f"-{SALARY_BAND_PENALTY} above-band: min={effective_low}")
    return (0, None)


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
        "adjustments": [],
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

    # Salary band adjustment — see _salary_band_penalty() docstring.
    # Penalty is a flat -5 applied AFTER the dimensions roll up, so it's
    # small enough not to dominate a strong rule-based score but visible
    # enough to push borderline-band roles below their neighbors.
    salary_adj, salary_reason = _salary_band_penalty(job)
    if salary_adj != 0:
        breakdown["adjustments"].append({
            "label": "salary band",
            "value": salary_adj,
            "reason": salary_reason,
        })

    total = max(0, min(100, round(weighted_total + salary_adj)))
    breakdown["total"] = total
    return (total, breakdown)
