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
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import budget, supabase_client

# Locked to Haiku 4.5 per §4.2.
MODEL = "claude-haiku-4-5"

# Base Haiku 4.5: $1 / $5 per MTok input/output. Batch API = 50% off.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50
# Cache-write (ephemeral, 5-min TTL): 1.25x base input.
# Cache-read: 0.1x base input. Batch discount composes with both.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

# Warm threshold — plan §1 design note #2. Below this is the
# rule-scored gatekeeper cutoff; we don't pay AI cost on cold jobs.
WARM_THRESHOLD = 60

# Cap per run. The cache's 5-min TTL means every ~250 requests is a new
# cache-write window; a single batch of 500 comfortably fits inside one
# window. Over 500 and we'd risk re-paying the write cost mid-batch.
MAX_JOBS_PER_RUN = 500

POLL_INTERVAL_SECONDS = 30
POLL_MAX_SECONDS = 25 * 60

DESCRIPTION_MAX_CHARS = 3000  # per §4.2

# §4.2: LOCKED system prompt prefix. The active CV text is inlined
# between the two `---` fences at runtime.
SYSTEM_PREFIX = (
    "You score Web3 job postings against a candidate's resume. Be honest. "
    "Inflated scores waste the candidate's time. "
    "Return JSON only, no prose, no code fences.\n\n"
    "CANDIDATE RESUME:\n---\n"
)
SYSTEM_SUFFIX = "\n---"

# §4.2: LOCKED user template.
USER_TEMPLATE = """Score this job against the candidate's resume above.

Job:
- Title: {title}
- Company: {company}
- Vertical: {vertical}
- Function: {function_category}
- Seniority: {seniority}
- Description: {description}

Return this exact shape:
{{
  "match_score": 0,
  "strengths": ["", "", ""],
  "gaps": ["", "", ""],
  "verdict_one_liner": ""
}}

Scoring rubric:
- 80-100: Strong match. Apply now. Resume already shows the required experience.
- 60-79:  Decent match. Worth tailoring CV for. Some required experience missing or weak.
- 40-59:  Weak match. Significant gaps. Only apply if you are willing to upskill or pivot.
- 0-39:   Not a match. Do not apply.

strengths: up to 3 items, each <= 80 chars, citing specific resume bullets that match the JD.
gaps: up to 3 items, each <= 80 chars, naming what's missing or weak.
verdict_one_liner: single sentence under 120 chars."""


def _get_anthropic_client():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  [fatal] ANTHROPIC_API_KEY missing", file=sys.stderr)
        return None
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError:
        print("  [fatal] anthropic SDK not installed", file=sys.stderr)
        return None
    try:
        return Anthropic(api_key=key)
    except Exception as e:
        print(f"  [fatal] Anthropic client init failed: {e}", file=sys.stderr)
        return None


def _fetch_active_resume(client) -> dict | None:
    if client is None:
        return None
    try:
        resp = (
            client.table("resumes")
            .select("id,parsed_text,char_count")
            .eq("is_active", True)
            .maybeSingle()
            .execute()
        )
        return getattr(resp, "data", None)
    except Exception as e:
        print(f"  [supabase] fetch active resume failed: {e}", file=sys.stderr)
        return None


def _fetch_already_scored_ids(client, resume_id: str) -> set[str]:
    """Job IDs this resume has already been scored against — skip them."""
    if client is None:
        return set()
    try:
        resp = (
            client.table("job_scores")
            .select("job_id")
            .eq("resume_id", resume_id)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        return {str(r["job_id"]) for r in rows}
    except Exception as e:
        print(f"  [supabase] fetch scored ids failed: {e}", file=sys.stderr)
        return set()


def _fetch_eligible_jobs(client, already_scored: set[str], limit: int) -> list[dict]:
    """score_total >= WARM, is_active = true, not already scored for this CV."""
    if client is None:
        return []
    # Overfetch so exclusion of `already_scored` still leaves us close to `limit`.
    fetch_limit = min(limit * 2, 1000)
    try:
        resp = (
            client.table("jobs")
            .select(
                "id,title,company,location,description,"
                "function_category,vertical,seniority"
            )
            .eq("is_active", True)
            .gte("score_total", WARM_THRESHOLD)
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
                "max_tokens": 500,
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


def _poll_batch(anthropic_client, batch_id: str):
    deadline = time.time() + POLL_MAX_SECONDS
    while time.time() < deadline:
        try:
            batch = anthropic_client.messages.batches.retrieve(batch_id)
        except Exception as e:
            print(f"  [anthropic] poll failed (will retry): {e}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        status = getattr(batch, "processing_status", None)
        counts = getattr(batch, "request_counts", None)
        print(f"  [poll] status={status}  counts={counts}")
        if status == "ended":
            return batch
        time.sleep(POLL_INTERVAL_SECONDS)
    print("  [poll] timed out — next cron run will pick up the pieces", file=sys.stderr)
    return None


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _extract_json(text: str) -> dict | None:
    stripped = _FENCE_RE.sub("", text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _clean_str_list(value, max_items: int = 3, max_chars: int = 80) -> list[str]:
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
    score = _clamp_match_score(parsed.get("match_score"))
    if score is None:
        return None
    verdict = parsed.get("verdict_one_liner")
    verdict = (verdict.strip()[:120] if isinstance(verdict, str) else None) or None
    return {
        "job_id": job_id,
        "resume_id": resume_id,
        "match_score": score,
        "strengths": _clean_str_list(parsed.get("strengths")),
        "gaps": _clean_str_list(parsed.get("gaps")),
        "verdict_one_liner": verdict,
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
        f"limit={args.limit}  dry={args.dry}"
    )

    sb = supabase_client.get_client()
    if sb is None and not args.dry:
        print("  [fatal] no Supabase client", file=sys.stderr)
        return 2

    try:
        budget.assert_under_budget(sb)
    except budget.BudgetExceeded as e:
        print(f"  [kill-switch] {e}", file=sys.stderr)
        return 3

    resume = _fetch_active_resume(sb) if sb else None
    if not resume:
        print("  no active resume — nothing to score")
        return 0
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
        print("  nothing eligible (no warm unscored jobs)")
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
