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
from scraper._anthropic_batch import (
    extract_json as _extract_json,
    get_anthropic_client as _get_anthropic_client,
    poll_batch as _poll_batch,
)

# Locked to Haiku 4.5 per §4.2. Use the alias (matches classify.py) so the
# Batch API resolves to the latest snapshot. If Anthropic retires the alias
# we'll get a clear error and can pin to a specific snapshot at that point.
MODEL = "claude-haiku-4-5"

# Base Haiku 4.5: $1 / $5 per MTok input/output. Batch API = 50% off.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50
# Cache-write (ephemeral, 5-min TTL): 1.25x base input.
# Cache-read: 0.1x base input. Batch discount composes with both.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

# Warm threshold — jobs below this rule-based score are skipped for AI scoring.
# Restored to 60 (the original spec value in COST_MATH.md / HANDOFF.md) after
# 40 was driving cv_score volume ~15x over the cost model. classify.py also
# uses 60 to skip cold jobs entirely; keep these two in sync.
WARM_THRESHOLD = 60

# Skip cv_score for jobs first seen more than this many days ago. The
# scrape pass keeps a job alive (is_active=true, last_seen_at refresh) for
# as long as the source still lists it, so a long-running posting stays in
# rotation. We don't need to keep paying to score every backlog row that
# was eligible weeks ago and never got scored — those are stale by now.
MAX_JOB_AGE_DAYS = 15

# Cap per run. The cache's 5-min TTL means every ~250 requests is a new
# cache-write window; a single batch of 500 comfortably fits inside one
# window. Over 500 and we'd risk re-paying the write cost mid-batch.
MAX_JOBS_PER_RUN = 500

DESCRIPTION_MAX_CHARS = 3000  # per §4.2

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
| industry_fit         |  30 | How close candidate's industry background is to role's vertical |
| title_alignment      |  15 | Role's primary function vs candidate's primary function (discipline, not level) |
| seniority            |  15 | Level fit, ownership model, scope of responsibility |
| requirements         |  15 | % of explicit must-haves met, weighted by centrality |
| geography            |  10 | Timezone fit, language mandates, remote policy |

### DIMENSION RULES
**skill_match (max 15):** Full match=100% contribution. Adjacent/transferable=50-90% transfer factor. Missing creative skills (video, graphic design) = -1 to -2 pts. Signature skills with measurable achievements = +1 to +2 boost if role requires them.

**industry_fit (max 30):** Exact vertical=26-30. Adjacent vertical=17-22. Partial match=10-16. Weak/no match=0-9. Web3/crypto/DeFi/GameFi/NFT/DAO roles get +15 pts applied as a POST-scoring adjustment (not in this dimension).

**title_alignment (max 15):** Perfect (same function category)=15. Similar (adjacent, meaningful overlap)=10. Long shot (different but evidenced bridge skill)=5. Mismatch=0-3. Determine from CV responsibilities, not just title.

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
- strengths: 2-4 bullets, each under 80 chars, citing specific resume evidence.
- gaps: 2-4 bullets, each under 80 chars.
- adjustments: list only adjustments that actually apply (can be empty list []).
- subtotal: sum of all 6 dimension scores before adjustments (max 100).
- final_score: clamp(subtotal + net adjustments, 0, 100).
"""


def _fetch_active_resume(client) -> dict | None:
    if client is None:
        return None
    try:
        resp = (
            client.table("resumes")
            .select("id,parsed_text,char_count")
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        return getattr(resp, "data", None)
    except Exception as e:
        print(f"  [supabase] fetch active resume failed: {e}", file=sys.stderr)
        return None


def _fetch_already_scored_ids(client, resume_id: str) -> set[str]:
    """Job IDs already scored with v5 breakdown for this resume — skip them.
    Jobs with score_breakdown_v5 IS NULL are re-eligible (old v4 rows)."""
    if client is None:
        return set()
    try:
        resp = (
            client.table("job_scores")
            .select("job_id")
            .eq("resume_id", resume_id)
            .not_("score_breakdown_v5", "is", "null")
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        return {str(r["job_id"]) for r in rows}
    except Exception as e:
        print(f"  [supabase] fetch scored ids failed: {e}", file=sys.stderr)
        return set()


def _fetch_eligible_jobs(client, already_scored: set[str], limit: int) -> list[dict]:
    """score_total >= WARM, is_active = true, first_seen within MAX_JOB_AGE_DAYS,
    not already scored for this CV."""
    if client is None:
        return []
    # Overfetch so exclusion of `already_scored` still leaves us close to `limit`.
    fetch_limit = min(limit * 2, 1000)
    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)
    ).isoformat()
    try:
        resp = (
            client.table("jobs")
            .select(
                "id,title,company,location,remote_status,description,"
                "function_category,vertical,seniority"
            )
            .eq("is_active", True)
            .gte("score_total", WARM_THRESHOLD)
            .gte("first_seen_at", cutoff_iso)
            .order("score_total", desc=True)
            .limit(fetch_limit)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
    except Exception as e:
        print(f"  [supabase] fetch eligible failed: {e}", file=sys.stderr)
        return []
    eligible = [r for r in rows if str(r["id"]) not in already_scored]
    return eligible[:limit]


def _build_user_message(job: dict) -> str:
    desc = (job.get("description") or "").strip()[:DESCRIPTION_MAX_CHARS]
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


def _build_batch_requests(jobs: list[dict], resume_text: str) -> list[dict]:
    """Build Batch requests. System is cached via cache_control: ephemeral."""
    system_block = {
        "type": "text",
        "text": SYSTEM_PREFIX + resume_text + SYSTEM_SUFFIX,
        "cache_control": {"type": "ephemeral"},
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
    try:
        return anthropic_client.messages.batches.create(requests=requests)
    except Exception as e:
        print(f"  [anthropic] batch create failed: {e}", file=sys.stderr)
        return None


def _clean_str_list(value, max_items: int = 4, max_chars: int = 80) -> list[str]:
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
            "score": int(cell.get("score") or 0),
            "notes": str(cell.get("notes") or "")[:80],
        }

    adjustments = []
    for adj in (parsed.get("adjustments") or []):
        if not isinstance(adj, dict):
            continue
        adjustments.append({
            "label": str(adj.get("label") or "")[:60],
            "value": int(adj.get("value") or 0),
        })

    breakdown = {
        "location_eligible": True,
        "subtotal": int(parsed.get("subtotal") or 0),
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
        print("  active resume text too short — skipping", file=sys.stderr)
        return 0
    print(f"  active resume={resume_id}  chars={len(resume_text)}")

    already = _fetch_already_scored_ids(sb, resume_id) if sb else set()
    print(f"  already scored for this CV: {len(already)}")

    jobs = _fetch_eligible_jobs(sb, already, args.limit) if sb else []
    if not jobs:
        print("  nothing eligible — no jobs with score_total >= "
              f"{WARM_THRESHOLD} that haven't been scored yet")
        return 0
    print(f"  {len(jobs)} jobs to score")

    if args.dry:
        payload = _build_batch_requests(jobs[:1], resume_text)
        print("\n  [dry] sample request (system truncated to 400 chars):")
        print("---")
        sys_text = payload[0]["params"]["system"][0]["text"]
        print(sys_text[:400] + ("…" if len(sys_text) > 400 else ""))
        print("---")
        print(payload[0]["params"]["messages"][0]["content"][:800])
        print("---")
        print(f"  [dry] would submit {len(jobs)} requests to Batch API")
        return 0

    anthropic = _get_anthropic_client()
    if anthropic is None:
        return 2

    payload = _build_batch_requests(jobs, resume_text)
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
    parse_failed = 0

    for result in anthropic.messages.batches.results(batch_id):
        custom_id = getattr(result, "custom_id", None)
        outcome = getattr(result, "result", None)
        outcome_type = getattr(outcome, "type", None)
        if outcome_type != "succeeded":
            errored += 1
            continue
        message = getattr(outcome, "message", None)
        if not message:
            errored += 1
            continue
        usage = getattr(message, "usage", None)
        if usage:
            input_tokens_total += getattr(usage, "input_tokens", 0) or 0
            cache_write_total += getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read_total += getattr(usage, "cache_read_input_tokens", 0) or 0
            output_tokens_total += getattr(usage, "output_tokens", 0) or 0
        text = ""
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                break
        parsed = _extract_json(text)
        if not parsed or custom_id not in job_ids:
            parse_failed += 1
            continue
        row = _parsed_to_row(parsed, custom_id, resume_id)
        if row is None:
            parse_failed += 1
            continue
        rows_to_write.append(row)
        ok += 1

    print(
        f"  [parse] ok={ok}  parse_failed={parse_failed}  errored={errored}  "
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
