"""CV scoring — Phase 6.

Scores every warm-or-better job (score_total >= 60) that has not yet been
scored against the currently active resume. Uses Claude Haiku 4.5 via
the Batch API (50% off base rates) + prompt caching on the system
message (~90% read discount on the CV text after the first request).

Prompt is LOCKED per JOB_SEARCH_AGENT_V3_PLAN.md §4.2. Do not improvise.

Pipeline:
    1. budget.assert_under_budget() — kill switch
    2. SELECT id, parsed_text FROM resumes WHERE is_active = true
       → no active CV ⇒ nothing to do
    3. Eligible jobs = score_total >= 60 AND is_active = true
       AND id NOT IN (SELECT job_id FROM job_scores WHERE resume_id=X)
    4. Build one Batch request per job. System = CV-enriched prompt
       with cache_control: ephemeral. User = per-job details.
    5. Submit batch, poll until 'ended'
    6. Parse JSON responses → upsert to job_scores
       (on_conflict: job_id,resume_id so reruns are idempotent)
    7. Log spend including cache_creation / cache_read token breakdown

Cost (§8): ~3500 cached-in + ~600 fresh-in + ~250 out per job.
    First request pays cache-write (1.25x input); rest pay cache-read (0.1x).
    ≈ $0.0009 per job with caching; ~180 backlog jobs ≈ $0.16.

Usage:
    python scraper/cv_score.py                # run
    python scraper/cv_score.py --limit 50     # cap
    python scraper/cv_score.py --dry          # build payload, skip AI call
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import budget, supabase_client
from scraper._prompt_safety import strip_injection as _strip_injection
from scraper._anthropic_batch import (
    extract_json as _extract_json,
    get_anthropic_client as _get_anthropic_client,
    poll_batch as _poll_batch,
)

# Locked to Haiku 4.5 per §4.2. Full versioned ID required by Batch API.
MODEL = "claude-haiku-4-5-20251001"

# Base Haiku 4.5: $1 / $5 per MTok input/output. Batch API = 50% off.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50
# Cache-write multiplier depends on TTL:
#   ephemeral (5-min) → 1.25× base input
#   ephemeral (1-hour) → 2.0×  base input
# Cache-read: 0.1× base input regardless of TTL. Batch discount composes
# with both.
#
# 2026-05-14: switched to 1-hour TTL after observing 0% cache-read MTD
# on /settings. Anthropic's Batch API parallelises requests across
# workers and queues them over windows much longer than 5 min, so the
# default 5-min TTL was producing per-job cache misses — every request
# paid for the full ~5k-token system block. With 530 jobs in a single
# day's backlog drain that was ~$2.04 instead of the ~$0.45 a healthy
# cache would have cost. 1-hour TTL costs more per WRITE (1.25× → 2.0×)
# but the read price stays flat, so net savings scale with batch size:
#   530-job batch: $1.59 saved (4.5× cheaper)
#    50-job batch (steady state): $0.03 saved (4.0× cheaper)
# See _build_batch_requests for the cache_control marker.
CACHE_WRITE_MULTIPLIER = 2.00  # was 1.25 (5-min TTL)
CACHE_READ_MULTIPLIER = 0.10

# Warm threshold — jobs below this rule-based score are skipped for AI scoring.
# Lowered from 60 → 40 (2026-05-13): the rule scorer is keyword-heavy on the
# title; creative Web3 titles like "Head of Brand", "Discord Lead",
# "Ecosystem Catalyst" were silently scoring 40-59 and never reaching the AI.
# At 40 we send substantially more jobs to Haiku, but the per-stage budget
# cap ($20/mo for cv_score; bumped from $5 then $12 during May remediation —
# see scraper/budget.py STAGE_BUDGETS for current values) absorbs it
# comfortably. classify.py uses the same constant; keep them in sync (it
# imports from here).
WARM_THRESHOLD = 40

# Skip cv_score for jobs first seen more than this many days ago. Bumped
# 15 → 30 (2026-05-13) to match retention.INACTIVE_AFTER_DAYS so newly-
# activated CVs can rescore the full active backlog (was stranding jobs
# first-seen 16-30 days ago after a CV swap).
MAX_JOB_AGE_DAYS = 30

# Cap per run. Default 1000 (bumped from 500 on 2026-05-13). The 5-min
# ephemeral cache TTL means a 1000-job batch may cross 2-3 cache-write
# windows and re-pay the write cost (~$1 extra one-time), but the
# total cost across N jobs is the same whether we run 1×1000 or 2×500 —
# 1000 just clears the queue in one cron day instead of two.
MAX_JOBS_PER_RUN = 1000

# Larger ceiling used automatically when we detect a "fresh CV" backlog
# (see ``_detect_backlog_mode()`` below). Triggered when there are very
# few job_scores rows for the active resume — usually because the CV
# was just activated. We have room to drain the queue in one go without
# tripping the $20/mo cv_score stage cap (see scraper/budget.py
# STAGE_BUDGETS — was $5 → $12 → $20 across the May remediation).
MAX_JOBS_BACKLOG_DRAIN = 2000

# When fewer than this many jobs are already scored for the active CV,
# treat as fresh-CV backlog and switch to MAX_JOBS_BACKLOG_DRAIN. 100
# is a comfortable margin above zero (covers the case where someone
# scored a tiny test batch before activating the new CV in earnest).
BACKLOG_MODE_THRESHOLD = 100

# ─── CV-aware rescue (audit H, 2026-05-13) ──────────────────────────────────
# Jobs with rule-score between RESCUE_FLOOR and WARM_THRESHOLD are
# below the AI-scoring cutoff, but if the description matches enough
# of the candidate's structured skills they get promoted into the
# batch anyway. Catches roles with creative titles whose rule-score
# is just-below-warm but content is actually a strong fit.
#
# Floor = WARM_THRESHOLD - 5 = 35 by default. Anything lower turns
# the rescue into a flood — most jobs scoring 30-34 are genuinely
# off-profile.
RESCUE_FLOOR = WARM_THRESHOLD - 5
# At least this many distinct skill-graph terms must appear in the
# job's title+description blob for a rescue. 3 is empirically a
# decent signal-to-noise ratio.
RESCUE_MIN_SKILL_HITS = 3
# Cap how many rescued jobs we add to ANY single batch. Even if the
# rescue pipeline finds 200 borderline matches, only the top RESCUE_CAP
# go in — keeps the AI cost bounded and lets the main eligible set
# stay the primary signal.
RESCUE_CAP_PER_RUN = 100

DESCRIPTION_MAX_CHARS = 3000  # per §4.2

# Audit H6 (2026-05-20) / C2-new (2026-05-20): prompt-injection strip.
# Moved to scraper/_prompt_safety.py so classify.py and cv_score.py
# share one regex — one diff to extend coverage for both callers.

SYSTEM_PREFIX = """\
You are a precise job fit scoring engine. Score job listings against the candidate resume below.
Apply every rule exactly. Return JSON only — no prose, no code fences.

## SCORING SYSTEM

### STEP 0.5 — LOCATION ELIGIBILITY FILTER (run first)
Extract the candidate's location from the CV. Extract the role's location requirement.
If the role fails (on-site/hybrid/region-restricted remote that excludes the candidate) → set final_score=0, location_eligible=false, skip all dimensions.
Pass cases: fully remote global, fully remote restricted to candidate's country/region, hybrid in candidate's city, location unspecified.

### DIMENSIONS (base total 100)
| Dimension            | Max | Measure |
|----------------------|-----|---------|
| skill_match          |  15 | How closely demonstrated skills match the role's daily tasks |
| industry_fit         |  20 | How close candidate's industry background is to role's vertical |
| title_alignment      |  25 | Role's primary function vs candidate's primary function (discipline, not level) |
| seniority            |  15 | Level fit, ownership model, scope of responsibility |
| requirements         |  15 | % of explicit must-haves met, weighted by centrality |
| geography            |  10 | Timezone fit, language mandates, remote policy |

### DIMENSION RULES
**skill_match (max 15):** Full match=100% contribution. Adjacent/transferable=50-90% transfer factor. Missing creative skills (video, graphic design) = -1 to -2 pts. Signature skills with measurable achievements = +1 to +2 boost if role requires them.

**industry_fit (max 20):** Exact vertical=18-20. Adjacent vertical=12-17. Partial match=7-11. Weak/no match=0-6. Web3/crypto/DeFi/GameFi/NFT/DAO roles get +15 pts applied as a POST-scoring adjustment (not in this dimension).

**title_alignment (max 25):** Perfect (same function category)=23-25. Similar (adjacent, meaningful overlap)=15-22. Long shot (different but evidenced bridge skill)=7-14. Mismatch=0-6. Determine from CV responsibilities, not just title.

**seniority (max 15):** Role below candidate's level = positive signal, do not penalize. Multi-function/solo operator evidence in CV = +2 if role requires it.

**requirements (max 15):** Central unmet must-have = -4 to -6 pts. Moderate unmet = -2 to -3. Peripheral unmet = -1. Do not penalize nice-to-haves.

**geography (max 10):** Timezone diff ≤6h = no penalty. Diff >6h = -2 to -4 pts. Role welcomes candidate's region = +1 to +2.

### ADJUSTMENTS (applied after summing dimensions)
| Trigger | Amount |
|---------|--------|
| Role is Web3/crypto/DeFi/blockchain/NFT/DAO | +15 |
| Mandatory language in CV at stated proficiency | +10 |
| Mandatory language absent from CV | -20 |
| Optional language in CV | +5 |
| 3+ core daily-work tools missing | -3 to -5 |

Final score = clamp(subtotal + net_adjustments, 0, 100).

CANDIDATE RESUME:
---
"""

SYSTEM_SUFFIX = "\n---"

# When a structured skill graph is available, the system prompt switches
# from "read this resume text" to "score against this graph". The model
# is explicitly told not to invent skills outside the graph, which
# eliminates the "job mentions Rust → infer candidate has Rust" failure
# mode and makes scoring reproducible across runs.
SYSTEM_PREFIX_GRAPH = SYSTEM_PREFIX.replace(
    "CANDIDATE RESUME:",
    "CANDIDATE SKILL GRAPH (a structured extraction from the resume — do NOT\n"
    "score skills not listed below; treat absence as a gap):",
)

USER_TEMPLATE = """\
Score this job against the candidate resume above.

Job:
- Title: {title}
- Company: {company}
- Location: {location}
- Remote status: {remote_status}
- Vertical: {vertical}
- Function: {function_category}
- Seniority: {seniority}
- Description: {description}

Return exactly this JSON shape (no extra keys, no code fences):
{{
  "location_eligible": true,
  "final_score": 0,
  "verdict": "",
  "subtotal": 0,
  "dimensions": {{
    "skill_match":      {{"score": 0, "notes": ""}},
    "industry_fit":     {{"score": 0, "notes": ""}},
    "title_alignment":  {{"score": 0, "notes": ""}},
    "seniority":        {{"score": 0, "notes": ""}},
    "requirements":     {{"score": 0, "notes": ""}},
    "geography":        {{"score": 0, "notes": ""}}
  }},
  "adjustments": [{{"label": "", "value": 0}}],
  "strengths": [""],
  "gaps": [""]
}}

Rules:
- If location_eligible is false: set final_score=0, omit dimensions/adjustments/strengths/gaps.
- verdict: one sentence, under 120 chars.
- Each dimension notes: under 80 chars.
- strengths: 2-4 bullets, each under 140 chars, citing specific resume evidence.
- gaps: 2-4 bullets, each under 140 chars.
- adjustments: list only adjustments that actually apply (can be empty list []).
- subtotal: sum of all 6 dimension scores before adjustments (max 100).
- final_score: clamp(subtotal + net adjustments, 0, 100).
"""


def _fetch_active_resume(client) -> dict | None:
    """Return the active CV row for PIPELINE_OWNER_USER_ID, or None.

    Audit H27: previously used ``.maybe_single()`` which RAISES if more
    than one row matches (e.g. mid-migration with two active resumes by
    accident). The exception bubbled up to the bare ``except``, which
    then logged a misleading "fetch active resume failed" instead of
    "you have multiple active resumes." Switch to ``.limit(1)`` so the
    function returns the first match deterministically even when the
    invariant is broken — operator can clean up at their leisure.

    Audit C2 (2026-05-19): scope the lookup by ``user_id`` so the
    pipeline only ever services the owner's CV. When
    ``PIPELINE_OWNER_USER_ID`` is unset we return None WITHOUT issuing
    a query — falling through to a global SELECT would re-introduce
    the bug. main() does an explicit fail-closed env check at startup
    so under normal operation this fallback is unreachable.
    """
    if client is None:
        return None
    owner_id = supabase_client.get_pipeline_owner_user_id()
    if not owner_id:
        print(
            "  [cv_score] PIPELINE_OWNER_USER_ID unset — refusing to issue "
            "a global resumes SELECT (audit C2)",
            file=sys.stderr,
        )
        return None
    # Select skill_graph too — cv_score prefers it over parsed_text when
    # present (see _resolve_cv_payload below). Gracefully degrades if the
    # column doesn't exist yet (pre-migration).
    select_cols = "id,parsed_text,char_count,skill_graph"
    try:
        resp = (
            client.table("resumes")
            .select(select_cols)
            .eq("user_id", owner_id)
            .eq("is_active", True)
            .order("id")  # deterministic tiebreaker if multiple are active
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        return rows[0] if rows else None
    except Exception as e:
        msg = str(e)
        # Column missing → retry without skill_graph (pre-migration env).
        if "skill_graph" in msg or "PGRST204" in msg or "42703" in msg:
            try:
                resp = (
                    client.table("resumes")
                    .select("id,parsed_text,char_count")
                    .eq("user_id", owner_id)
                    .eq("is_active", True)
                    .order("id")
                    .limit(1)
                    .execute()
                )
                rows = getattr(resp, "data", None) or []
                return rows[0] if rows else None
            except Exception as e2:
                print(f"  [supabase] fetch active resume failed: {e2}", file=sys.stderr)
                return None
        print(f"  [supabase] fetch active resume failed: {e}", file=sys.stderr)
        return None


def _fetch_already_scored_ids(client, resume_id: str) -> set[str]:
    """Job IDs already scored with v5 breakdown for this resume — skip them.
    Jobs with score_breakdown_v5 IS NULL are re-eligible (old v4 rows).

    Paginates the fetch because PostgREST applies a hard server-side
    `Range` cap (default 1000 rows) to every unbounded `.select()`. The
    previous one-shot fetch silently truncated at 1000 — so when more
    than 1000 jobs had already been scored against the active CV, the
    leftover already-scored IDs were missing from the exclusion set and
    `_fetch_eligible_jobs` happily handed those rows back to the batch
    to be re-scored. Observed on 2026-05-16: 1418 scored jobs in DB,
    only 1000 returned to the exclusion set, ~400 re-scored unnecessarily.
    """
    if client is None:
        return set()
    seen: set[str] = set()
    PAGE = 1000
    HARD_CAP = 100_000  # safety — never page beyond this many rows
    offset = 0
    try:
        while offset < HARD_CAP:
            resp = (
                client.table("job_scores")
                .select("job_id")
                .eq("resume_id", resume_id)
                .filter("score_breakdown_v5", "not.is", "null")
                .range(offset, offset + PAGE - 1)  # inclusive both ends
                .execute()
            )
            rows = getattr(resp, "data", []) or []
            if not rows:
                break
            for r in rows:
                seen.add(str(r["job_id"]))
            if len(rows) < PAGE:
                break  # last page
            offset += PAGE
    except Exception as e:
        print(f"  [supabase] fetch scored ids failed: {e}", file=sys.stderr)
        # Fail-soft: return what we already paged in. Better to over-skip
        # than under-skip — the alternative is re-scoring duplicates.
    return seen


def _fetch_eligible_jobs(client, already_scored: set[str], limit: int) -> list[dict]:
    """score_total >= WARM, is_active = true, geo_filtered = true,
    first_seen within MAX_JOB_AGE_DAYS, not already scored for this CV.

    Pages through the candidate set top-down and excludes already_scored
    *during iteration* — not after a single fixed window. The previous
    "fetch top-1000, then post-filter" approach broke once the high-score
    band was mostly already scored: the window filled with already-scored
    rows and only a tiny residue survived the post-filter, leaving the
    long tail of unscored eligibles permanently below the cutoff.

    Concretely on Eugenio's data 2026-05-04: 1418 of the top-1000-by-score
    were already scored, so a typical run would only see the 45 unscored
    rows that happened to fall in that window — even though 459 unscored
    eligible jobs existed in the DB.

    PostgREST's URL length precludes a `not_.in_("id", <huge list>)`
    server-side anti-join (Supabase's PostgREST caps at ~8KB; UUID lists
    of >200 items overflow). Pagination + client-side exclusion is the
    next-cleanest pattern and bounds DB load by HARD_CAP.
    """
    if client is None:
        return []
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)
    ).isoformat()

    PAGE = 500
    HARD_CAP = 5000  # safety: never page beyond this many rows in one run
    eligible: list[dict] = []
    offset = 0

    try:
        while len(eligible) < limit and offset < HARD_CAP:
            resp = (
                client.table("jobs")
                .select(
                    "id,title,company,location,remote_status,description,"
                    "function_category,vertical,seniority"
                )
                .eq("is_active", True)
                .eq("geo_filtered", True)   # only jobs that passed geo_filter
                .gte("score_total", WARM_THRESHOLD)
                .gte("first_seen_at", cutoff_iso)
                .order("score_total", desc=True)
                # Audit H26: secondary sort key. Without it, rows that tie
                # on score_total can drift across pages and either get
                # skipped or appear in two adjacent windows. ``id`` is
                # unique, so pagination is stable.
                .order("id", desc=False)
                .range(offset, offset + PAGE - 1)  # inclusive on both ends
                .execute()
            )
            rows = getattr(resp, "data", []) or []
            if not rows:
                break  # no more candidates
            for r in rows:
                if str(r["id"]) not in already_scored:
                    eligible.append(r)
                    if len(eligible) >= limit:
                        break
            offset += PAGE
    except Exception as e:
        print(f"  [supabase] fetch eligible failed: {e}", file=sys.stderr)
        # Fail-soft: return what we accumulated before the failure rather
        # than dropping a partial backlog scan on the floor.
        return eligible

    # Audit M2 (2026-05-14): warn when HARD_CAP exits with a still-short
    # eligible list. Previously the loop bailed silently — after a CV
    # swap with 10k unscored eligible jobs (lowered WARM_THRESHOLD,
    # rescore_recent.py clearing job_scores), the second half of the
    # backlog never surfaced. ``::warning::`` lands as a yellow
    # annotation on the workflow run in GitHub Actions.
    if offset >= HARD_CAP and len(eligible) < limit:
        print(
            f"::warning::cv_score paged through HARD_CAP={HARD_CAP} rows but only "
            f"found {len(eligible)} unscored eligible jobs (asked for {limit}). "
            "Remaining backlog will be picked up on subsequent runs."
        )

    return eligible[:limit]


def _skill_terms_from_graph(skill_graph: dict | None) -> list[str]:
    """Extract lower-cased skill names from a stored skill_graph row.
    Used by ``_fetch_rescue_candidates`` to do the title+description
    keyword sniff. Filters out very short tokens that would match
    spuriously (e.g. "C", "Go").
    """
    if not isinstance(skill_graph, dict):
        return []
    skills = skill_graph.get("skills") or []
    out: list[str] = []
    for s in skills:
        if not isinstance(s, dict):
            continue
        name = (s.get("name") or "").strip().lower()
        if len(name) >= 3:
            out.append(name)
    return out


def _fetch_rescue_candidates(
    client,
    already_scored: set[str],
    skill_terms: list[str],
    limit: int,
) -> list[dict]:
    """Pull borderline jobs (RESCUE_FLOOR <= score_total < WARM_THRESHOLD)
    whose title+description contains at least RESCUE_MIN_SKILL_HITS
    distinct skill_graph terms.

    Returns up to ``limit`` rows in score_total-desc order. Filters
    is_active + geo_filtered same as the primary fetch, so a rescued
    job has cleared every other gate — only the rule-score was a hair
    below warm.

    Returns [] (silently) if the skill_graph is empty or missing, so
    pre-extraction runs gracefully skip the rescue without erroring.
    """
    if client is None or not skill_terms or limit <= 0:
        return []
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)
    ).isoformat()

    PAGE = 500
    HARD_CAP = 5000
    out: list[dict] = []
    offset = 0

    try:
        while len(out) < limit and offset < HARD_CAP:
            resp = (
                client.table("jobs")
                .select(
                    "id,title,company,location,remote_status,description,"
                    "function_category,vertical,seniority"
                )
                .eq("is_active", True)
                .eq("geo_filtered", True)
                .gte("score_total", RESCUE_FLOOR)
                .lt("score_total", WARM_THRESHOLD)
                .gte("first_seen_at", cutoff_iso)
                .order("score_total", desc=True)
                .order("id", desc=False)
                .range(offset, offset + PAGE - 1)
                .execute()
            )
            rows = getattr(resp, "data", []) or []
            if not rows:
                break
            for r in rows:
                if str(r["id"]) in already_scored:
                    continue
                blob = (
                    (r.get("title") or "") + " " + (r.get("description") or "")
                ).lower()
                hits = sum(1 for t in skill_terms if t in blob)
                if hits >= RESCUE_MIN_SKILL_HITS:
                    out.append(r)
                    if len(out) >= limit:
                        break
            offset += PAGE
    except Exception as e:
        print(f"  [supabase] rescue fetch failed: {e}", file=sys.stderr)
        return out

    return out[:limit]


def _build_user_message(job: dict) -> str:
    raw_desc = (job.get("description") or "").strip()[:DESCRIPTION_MAX_CHARS]
    # Audit H6: strip injection phrases before the description enters the prompt.
    desc = _strip_injection(raw_desc)
    return USER_TEMPLATE.format(
        title=(job.get("title") or "")[:300],
        company=(job.get("company") or "Unknown"),
        location=(job.get("location") or "Unspecified"),
        remote_status=(job.get("remote_status") or "Unspecified"),
        vertical=(job.get("vertical") or "Unspecified"),
        function_category=(job.get("function_category") or "Unspecified"),
        seniority=(job.get("seniority") or "Unspecified"),
        description=desc or "(no description available)",
    )


def _resolve_cv_payload(resume: dict, supabase_client, anthropic_client) -> tuple[str, str]:
    """Decide what to put in the system prompt: structured skill graph
    (preferred) or raw parsed_text (legacy fallback).

    Resolution:
      1. If resume.skill_graph is a non-empty dict → use it.
      2. Else attempt lazy extraction via cv_extract.extract_and_store_skill_graph;
         on success, use the new graph.
      3. Else fall back to parsed_text.

    Returns (mode, payload_string) where mode is "graph" or "text".

    Audit H4 (2026-05-14): CV-swap-during-cv_score behaviour. The
    ``resume`` dict was captured at the start of ``main()`` by
    ``_fetch_active_resume``. If the user activates a different CV on
    the web app while this run is in flight, the new resume's data is
    NOT picked up — the current run finishes scoring against the
    captured resume_id. This is intentional (avoid half-scoring a
    batch against two CVs and writing inconsistent job_scores rows),
    but worth knowing if you ever see "I activated CV B but cv_score
    still wrote scores under CV A's id." The next pipeline tick will
    pick up CV B cleanly.
    """
    import json as _json
    from scraper.cv_extract import extract_and_store_skill_graph

    graph = resume.get("skill_graph") if isinstance(resume, dict) else None
    if isinstance(graph, dict) and graph:
        return ("graph", _json.dumps(graph, ensure_ascii=False, indent=2))

    parsed_text = (resume.get("parsed_text") or "").strip()
    if anthropic_client is not None and parsed_text:
        resume_id = str(resume.get("id") or "")
        if resume_id:
            print(
                "  [cv_score] no skill_graph on resume — extracting once "
                "(stored for next run)…"
            )
            extracted = extract_and_store_skill_graph(
                supabase_client, anthropic_client, resume_id, parsed_text,
            )
            if extracted:
                return ("graph", _json.dumps(extracted, ensure_ascii=False, indent=2))

    # Legacy path: just dump the parsed text.
    return ("text", parsed_text)


def _build_batch_requests(jobs: list[dict], cv_payload: tuple[str, str]) -> list[dict]:
    """Build Batch requests. System is cached via cache_control: ephemeral.

    ``cv_payload`` is (mode, content) from _resolve_cv_payload. The system
    prompt prefix changes based on mode so the model knows whether it's
    looking at a structured graph (and must not invent skills) or at raw
    CV text (legacy free-form interpretation).
    """
    mode, content = cv_payload
    prefix = SYSTEM_PREFIX_GRAPH if mode == "graph" else SYSTEM_PREFIX
    system_block = {
        "type": "text",
        "text": prefix + content + SYSTEM_SUFFIX,
        # 2026-05-14: switched from default 5-min TTL to explicit 1-hour
        # TTL after MTD cache-read rate was observed at 0% on /settings.
        # Batch API parallelises requests over windows much longer than
        # 5 min; the default TTL was expiring before subsequent requests
        # could read it, so every job was paying for the full system
        # block. 1-hour TTL costs 1.6× more per WRITE but reads stay
        # flat, so any batch ≥ ~5 jobs is net cheaper.
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }
    out = []
    for job in jobs:
        out.append({
            "custom_id": str(job["id"]),
            "params": {
                "model": MODEL,
                "max_tokens": 800,
                "system": [system_block],
                "messages": [
                    {"role": "user", "content": _build_user_message(job)}
                ],
            },
        })
    return out


def _submit_batch(anthropic_client, requests: list[dict]):
    """Submit a Batch with the 1-hour-TTL caching beta enabled.

    The system block in `_build_batch_requests` carries `cache_control:
    {"type": "ephemeral", "ttl": "1h"}` to extend the default 5-min cache
    TTL to 1 hour — Batch API parallelises across workers over windows
    much longer than 5 min, so the default TTL produced 0 cache hits.

    BUT the `ttl: "1h"` field is silently ignored unless the request
    carries the `anthropic-beta: extended-cache-ttl-2025-04-11` header.
    Observed on 2026-05-16: a 1000-job batch reported
    cache_creation_input_tokens=0 + cache_read_input_tokens=0 → entire
    batch billed as fresh input ($1.95 vs an expected ~$0.45 with cache
    actually working). Reading the SDK source / docs confirms the beta
    flag is required for the extended-TTL feature, which is still in
    beta as of mid-2026.
    """
    try:
        return anthropic_client.messages.batches.create(
            requests=requests,
            extra_headers={"anthropic-beta": "extended-cache-ttl-2025-04-11"},
        )
    except Exception as e:
        print(f"  [anthropic] batch create failed: {e}", file=sys.stderr)
        return None


def _clean_str_list(value, max_items: int = 4, max_chars: int = 140) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s:
            continue
        out.append(s[:max_chars])
    return out


def _clamp_match_score(value) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return 0
    if n > 100:
        return 100
    return n


def _safe_int(v, default: int = 0) -> int:
    """Coerce model output to int without ever raising.

    Audit C8: ``int(cell.get("score") or 0)`` raises ValueError on any
    non-integer string ("7.5", "ten", "")  and the exception propagated
    out of the result iterator below, aborting the *entire* batch
    write-back. We accept floats (truncate) and string-floats; anything
    else falls back to ``default``.
    """
    if v is None:
        return default
    if isinstance(v, bool):
        # ``isinstance(True, int)`` is True in Python — handle first.
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def _parsed_to_row(parsed: dict, job_id: str, resume_id: str) -> dict | None:
    # location filter — score 0 is valid and intentional
    location_eligible = parsed.get("location_eligible")
    if location_eligible is False:
        verdict = parsed.get("verdict")
        verdict = (verdict.strip()[:120] if isinstance(verdict, str) else None) or None
        return {
            "job_id": job_id,
            "resume_id": resume_id,
            "match_score": 0,
            "strengths": [],
            "gaps": [],
            "verdict_one_liner": verdict,
            "score_breakdown_v5": {"location_eligible": False},
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    score = _clamp_match_score(parsed.get("final_score"))
    if score is None:
        return None

    verdict = parsed.get("verdict")
    verdict = (verdict.strip()[:120] if isinstance(verdict, str) else None) or None

    # Build breakdown blob — store everything for the UI
    dims_raw = parsed.get("dimensions") or {}
    dims = {}
    for key in ("skill_match", "industry_fit", "title_alignment", "seniority", "requirements", "geography"):
        cell = dims_raw.get(key) or {}
        dims[key] = {
            "score": _safe_int(cell.get("score")),
            "notes": str(cell.get("notes") or "")[:80],
        }

    adjustments = []
    for adj in (parsed.get("adjustments") or []):
        if not isinstance(adj, dict):
            continue
        adjustments.append({
            "label": str(adj.get("label") or "")[:60],
            "value": _safe_int(adj.get("value")),
        })

    breakdown = {
        "location_eligible": True,
        "subtotal": _safe_int(parsed.get("subtotal")),
        "dimensions": dims,
        "adjustments": adjustments,
        "strengths": _clean_str_list(parsed.get("strengths")),
        "gaps": _clean_str_list(parsed.get("gaps")),
    }

    return {
        "job_id": job_id,
        "resume_id": resume_id,
        "match_score": score,
        "strengths": _clean_str_list(parsed.get("strengths")),
        "gaps": _clean_str_list(parsed.get("gaps")),
        "verdict_one_liner": verdict,
        "score_breakdown_v5": breakdown,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def _upsert_scores(client, rows: list[dict]) -> int:
    """on_conflict: (job_id, resume_id) — idempotent reruns."""
    if client is None or not rows:
        return 0
    written = 0
    BATCH = 200
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        try:
            resp = (
                client.table("job_scores")
                .upsert(chunk, on_conflict="job_id,resume_id")
                .execute()
            )
            got = len(resp.data) if getattr(resp, "data", None) else len(chunk)
            written += got
        except Exception as e:
            print(f"  [supabase] job_scores upsert failed: {e}", file=sys.stderr)
    return written


def _compute_cost(
    *,
    input_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
) -> float:
    c = (
        (input_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK
        + (cache_write_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK * CACHE_WRITE_MULTIPLIER
        + (cache_read_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK * CACHE_READ_MULTIPLIER
        + (output_tokens / 1_000_000) * BATCH_OUTPUT_PER_MTOK
    )
    return round(c, 6)


def _log_spend(
    client,
    *,
    input_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    cost_usd: float,
    notes: str,
) -> None:
    if client is None:
        return
    # spend_tracking columns: input_tokens, cached_input_tokens, output_tokens.
    # We pack cache_read under cached_input_tokens and put cache_write in
    # the notes so the MTD sum in budget.py stays driven by cost_usd.
    row = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "operation": "cv_score",
        "model": MODEL,
        "input_tokens": input_tokens + cache_write_tokens,
        "cached_input_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "notes": (f"cache_write={cache_write_tokens} " + notes)[:500],
    }
    try:
        client.table("spend_tracking").insert(row).execute()
    except Exception as e:
        print(f"  [supabase] spend_tracking insert failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Score warm jobs against the active CV.")
    ap.add_argument("--limit", type=int, default=MAX_JOBS_PER_RUN)
    ap.add_argument("--dry", action="store_true",
                    help="don't call Anthropic, don't write back")
    args = ap.parse_args()

    print(
        f"cv_score — started={datetime.now(timezone.utc).isoformat()}  "
        f"limit={args.limit}  dry={args.dry}  model={MODEL}"
    )

    # Startup env check — shows in Actions log so missing secrets are obvious.
    has_sb_url  = bool(os.environ.get("SUPABASE_URL"))
    has_sb_key  = bool(os.environ.get("SUPABASE_SERVICE_KEY"))
    has_ai_key  = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(
        f"  [env] SUPABASE_URL={'SET' if has_sb_url else 'MISSING'}  "
        f"SUPABASE_SERVICE_KEY={'SET' if has_sb_key else 'MISSING'}  "
        f"ANTHROPIC_API_KEY={'SET' if has_ai_key else 'MISSING'}"
    )
    if not has_sb_url or not has_sb_key:
        print("  [fatal] Supabase secrets missing — add SUPABASE_URL and SUPABASE_SERVICE_KEY "
              "to GitHub repo Settings → Secrets and variables → Actions", file=sys.stderr)
        return 2
    if not has_ai_key and not args.dry:
        print("  [fatal] ANTHROPIC_API_KEY missing — add it to GitHub repo "
              "Settings → Secrets and variables → Actions", file=sys.stderr)
        return 2

    # Audit C2 (2026-05-19): fail-closed if the single-tenant lock isn't
    # set. Otherwise _fetch_active_resume would refuse anyway, but a
    # clear early error beats "no active resume found" for diagnostics.
    if not supabase_client.get_pipeline_owner_user_id():
        print(
            "  [fatal] PIPELINE_OWNER_USER_ID missing — refusing to run. "
            "Set it to the Supabase auth.users.id of the pipeline owner "
            "in GitHub repo Settings → Secrets and variables → Actions. "
            "(See REVIEW.md C2.)",
            file=sys.stderr,
        )
        return 2

    sb = supabase_client.get_client()
    if sb is None and not args.dry:
        print("  [fatal] Supabase client init failed (check SUPABASE_URL / SUPABASE_SERVICE_KEY values)", file=sys.stderr)
        return 2

    try:
        budget.assert_under_budget(sb, operation="cv_score")
    except budget.BudgetExceeded as e:
        print(f"  [kill-switch] {e}", file=sys.stderr)
        return 3

    resume = _fetch_active_resume(sb) if sb else None
    if not resume:
        print("  [fatal] no active resume found — either Supabase credentials are wrong "
              "(check SUPABASE_SERVICE_KEY is the service-role key, not the anon key) "
              "or no CV has been activated on the Resume page", file=sys.stderr)
        return 1
    resume_id = str(resume["id"])
    resume_text = (resume.get("parsed_text") or "").strip()
    if len(resume_text) < 100:
        # Audit L5 (2026-05-14): return non-zero so the workflow fails
        # and notify_on_failure fires. A short / unparseable resume is a
        # config error, not a normal no-op — without this exit, cv_score
        # would silently emit nothing for days and the operator would
        # only notice via "the dashboard looks stale".
        print(
            "::error::active resume text too short (<100 chars) — "
            "re-upload the CV or check parsing on /resume",
            file=sys.stderr,
        )
        return 1
    print(f"  active resume={resume_id}  chars={len(resume_text)}")

    already = _fetch_already_scored_ids(sb, resume_id) if sb else set()
    print(f"  already scored for this CV: {len(already)}")

    # Backlog-mode auto-bump: if very few jobs are scored for this CV
    # (typical after a CV swap or after we lowered WARM_THRESHOLD), use
    # the larger limit so we drain the queue in one cron day instead of
    # spreading it across multiple. CLI --limit always wins.
    effective_limit = args.limit
    cli_limit_explicit = args.limit != MAX_JOBS_PER_RUN
    if not cli_limit_explicit and len(already) < BACKLOG_MODE_THRESHOLD:
        effective_limit = MAX_JOBS_BACKLOG_DRAIN
        print(
            f"  backlog mode: scored={len(already)} < {BACKLOG_MODE_THRESHOLD} "
            f"→ raising limit {MAX_JOBS_PER_RUN}→{effective_limit} for this run"
        )

    jobs = _fetch_eligible_jobs(sb, already, effective_limit) if sb else []
    primary_count = len(jobs)

    # Audit H (2026-05-13): CV-aware rescue — borderline jobs (35-39)
    # that hit 3+ skill_graph terms get pulled in despite rule-score
    # below WARM_THRESHOLD. The rescue pulls up to RESCUE_CAP_PER_RUN
    # extra rows OR enough to backfill the unused capacity from the
    # primary fetch — whichever is smaller. Keeps the batch within
    # ``effective_limit``.
    rescue_budget = min(RESCUE_CAP_PER_RUN, max(0, effective_limit - len(jobs)))
    if sb and rescue_budget > 0:
        skill_terms = _skill_terms_from_graph(resume.get("skill_graph"))
        if skill_terms:
            rescued = _fetch_rescue_candidates(sb, already, skill_terms, rescue_budget)
            if rescued:
                # Tag rescued jobs so the parse loop / logs can tell them
                # apart from primary picks. Doesn't affect cv_score's prompt.
                for r in rescued:
                    r["_rescued"] = True
                jobs.extend(rescued)
                print(
                    f"  rescue: +{len(rescued)} borderline jobs "
                    f"(score {RESCUE_FLOOR}-{WARM_THRESHOLD - 1}, "
                    f">= {RESCUE_MIN_SKILL_HITS} skill matches)"
                )
        else:
            print("  rescue: skipped (skill_graph empty — will fill on next run)")

    if not jobs:
        print("  nothing eligible — no jobs with score_total >= "
              f"{WARM_THRESHOLD} that haven't been scored yet "
              f"(and no rescue candidates between {RESCUE_FLOOR} and {WARM_THRESHOLD})")
        return 0
    print(f"  {len(jobs)} jobs to score "
          f"(primary={primary_count} rescued={len(jobs) - primary_count})")

    # We need the Anthropic client for both lazy skill-graph extraction
    # AND the batch submission. Initialise it once here and pass through.
    anthropic_for_extract = None
    if not args.dry:
        anthropic_for_extract = _get_anthropic_client()
        if anthropic_for_extract is None:
            return 2
    cv_payload = _resolve_cv_payload(resume, sb, anthropic_for_extract)
    print(f"  cv payload mode={cv_payload[0]}  chars={len(cv_payload[1])}")

    if args.dry:
        payload = _build_batch_requests(jobs[:1], cv_payload)
        print("\n  [dry] sample request (system truncated to 400 chars):")
        print("---")
        sys_text = payload[0]["params"]["system"][0]["text"]
        print(sys_text[:400] + ("…" if len(sys_text) > 400 else ""))
        print("---")
        print(payload[0]["params"]["messages"][0]["content"][:800])
        print("---")
        print(f"  [dry] would submit {len(jobs)} requests to Batch API")
        return 0

    # Reuse the client we created above for skill-graph extraction
    # rather than spawning a second one — same key, same connection
    # pool, simpler code path.
    anthropic = anthropic_for_extract or _get_anthropic_client()
    if anthropic is None:
        return 2

    payload = _build_batch_requests(jobs, cv_payload)
    batch = _submit_batch(anthropic, payload)
    if batch is None:
        return 4
    batch_id = batch.id
    print(f"  [anthropic] batch submitted: {batch_id}")

    final = _poll_batch(anthropic, batch_id)
    if final is None:
        print("  [anthropic] batch never ended — aborting write-back", file=sys.stderr)
        return 4

    input_tokens_total = 0
    cache_write_total = 0
    cache_read_total = 0
    output_tokens_total = 0
    rows_to_write: list[dict] = []
    job_ids = {str(j["id"]) for j in jobs}
    ok = 0
    errored = 0
    # Audit M2: split the old `parse_failed` counter. Conflating JSON parse
    # errors with "model returned an unknown custom_id" made the metric
    # useless for diagnosis. Keep them apart.
    json_parse_failed = 0
    unknown_custom_id = 0
    row_build_failed = 0

    def _record_usage(msg) -> None:
        """Pull token usage off any message-shaped object. Audit M1:
        previously we only counted on outcome_type='succeeded', but
        Anthropic charges input tokens for errored requests too, so the
        budget tracker silently drifted down with even a 1-2% error rate.
        Counting from every message present (succeeded OR errored)
        restores accuracy.
        """
        nonlocal input_tokens_total, cache_write_total, cache_read_total, output_tokens_total
        usage = getattr(msg, "usage", None)
        if not usage:
            return
        input_tokens_total += getattr(usage, "input_tokens", 0) or 0
        cache_write_total += getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read_total += getattr(usage, "cache_read_input_tokens", 0) or 0
        output_tokens_total += getattr(usage, "output_tokens", 0) or 0

    for result in anthropic.messages.batches.results(batch_id):
        custom_id = getattr(result, "custom_id", None)
        outcome = getattr(result, "result", None)
        outcome_type = getattr(outcome, "type", None)
        message = getattr(outcome, "message", None)
        # Always try to record usage — Anthropic bills input tokens even
        # when outcome_type is "errored", so skipping here is what made
        # the budget log under-count (M1).
        if message is not None:
            _record_usage(message)
        if outcome_type != "succeeded" or message is None:
            errored += 1
            continue
        text = ""
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                break
        if custom_id not in job_ids:
            # Contract violation — Anthropic returned a custom_id we
            # didn't submit. Not a parse failure (would be a model bug
            # or a wiring bug), so track separately.
            unknown_custom_id += 1
            continue
        parsed = _extract_json(text)
        if not parsed:
            json_parse_failed += 1
            continue
        # Audit C8: even with _safe_int below, a malformed model output
        # (unexpected nested type, etc.) shouldn't be allowed to escape
        # this iterator. Catching ensures one bad row never aborts the
        # whole 500-row write-back.
        try:
            row = _parsed_to_row(parsed, custom_id, resume_id)
        except Exception as e:
            print(
                f"  [parse] custom_id={custom_id} threw {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            row_build_failed += 1
            continue
        if row is None:
            row_build_failed += 1
            continue
        rows_to_write.append(row)
        ok += 1

    # Roll up the three failure counters for backwards-compat log greps
    # while keeping the breakdown visible.
    parse_failed = json_parse_failed + row_build_failed + unknown_custom_id
    print(
        f"  [parse] ok={ok}  parse_failed={parse_failed}  "
        f"(json={json_parse_failed} build={row_build_failed} "
        f"unknown_id={unknown_custom_id})  errored={errored}  "
        f"input={input_tokens_total}  cache_write={cache_write_total}  "
        f"cache_read={cache_read_total}  output={output_tokens_total}"
    )

    written = _upsert_scores(sb, rows_to_write)
    cost = _compute_cost(
        input_tokens=input_tokens_total,
        cache_write_tokens=cache_write_total,
        cache_read_tokens=cache_read_total,
        output_tokens=output_tokens_total,
    )
    print(f"  [writeback] {written}/{len(rows_to_write)} rows upserted  cost=${cost}")

    _log_spend(
        sb,
        input_tokens=input_tokens_total,
        cache_write_tokens=cache_write_total,
        cache_read_tokens=cache_read_total,
        output_tokens=output_tokens_total,
        cost_usd=cost,
        notes=(
            f"batch_id={batch_id} resume_id={resume_id} jobs={len(jobs)} "
            f"ok={ok} parse_failed={parse_failed} errored={errored}"
        ),
    )

    print(f"done: {datetime.now(timezone.utc).isoformat()}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
