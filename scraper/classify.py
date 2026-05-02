"""Classification — Phase 3.

Pulls jobs with function_category IS NULL, submits them to Claude Haiku 4.5
via the Batch API (50% off), polls for completion, writes structured
fields back to the jobs table, and logs spend to spend_tracking.

Prompt is LOCKED per JOB_SEARCH_AGENT_V3_PLAN.md §4.1. Do not improvise.

Pipeline:
    1. budget.assert_under_budget() — kill switch
    2. SELECT id, title, company, location, description, salary_source
       FROM jobs WHERE function_category IS NULL LIMIT MAX_JOBS_PER_RUN
    3. Build one Batch request per job (custom_id=job.id)
    4. Submit batch, poll processing_status until 'ended'
    5. Stream results: JSON-parse each, clamp to allowed enums, update row
    6. Insert a spend_tracking row with tokens + USD

Cost (§8): ~400 in + ~80 out * 300 jobs/mo ≈ $0.06/mo.

Usage:
    python scraper/classify.py                  # run against Supabase + Anthropic
    python scraper/classify.py --limit 50       # cap this run
    python scraper/classify.py --dry            # fetch + build prompt, no AI call
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Support both `python scraper/classify.py` and `python -m scraper.classify`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import budget, supabase_client
from scraper._anthropic_batch import (
    extract_json as _extract_json,
    get_anthropic_client as _get_anthropic_client,
    poll_batch as _poll_batch,
)

# §4 locks Haiku 4.5 as the classifier model. Alias resolves to the latest
# snapshot; if Anthropic retires it we get a clear error and can pin.
MODEL = "claude-haiku-4-5"

# Batch API = 50% of base rates. Haiku 4.5 base is $1/$5 per MTok,
# so Batch is $0.50/$2.50. Prices in USD per 1M tokens.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50

# Cap per run. 500 * $0.0004/job = $0.20 max — well under budget even if
# every single job in the backlog were fresh. Prevents a runaway first
# run if classification somehow fell behind for weeks.
MAX_JOBS_PER_RUN = 500

# Only classify jobs that would be cv_score candidates anyway. Cold jobs
# (rule score below the warm threshold) never get cv_scored, and the
# function_category they'd produce is never read. Keep this in sync with
# cv_score.WARM_THRESHOLD — both should be the same number.
CLASSIFY_MIN_SCORE = 60

# §4.1: LOCKED system prompt. Do not edit.
SYSTEM_PROMPT = (
    "You extract structured fields from Web3 job postings. "
    "Return JSON only, no prose, no code fences."
)

# §4.1: LOCKED user template. Do not edit.
USER_TEMPLATE = """Title: {title}
Company: {company}
Location: {location}
Description: {description}

Return this exact shape:
{{
  "function_category": "Community" | "Design" | "Engineering" | "Marketing" | "Operations" | "Sales" | "BizDev" | "Product" | "Other",
  "function_confidence": 0.0,
  "seniority": "Junior" | "Mid" | "Senior" | "Lead" | "Head" | "Executive" | "Unspecified",
  "vertical": "DeFi" | "L1" | "L2" | "CEX" | "DEX" | "Gaming" | "Infrastructure" | "NFT" | "RWA" | "Oracles" | "AI-Crypto" | "Other",
  "salary_min_usd": null,
  "salary_max_usd": null,
  "remote_status": "Remote" | "Hybrid" | "Onsite" | "Unspecified"
}}

Rules:
- Use Unspecified, Other, or null when genuinely uncertain. Do not guess.
- Salary fields only filled when explicitly stated in the description (numbers + USD or unambiguous currency).
- function_confidence is your confidence in function_category from 0.0 to 1.0."""

# §4.1 user template says "description_first_2000_chars".
DESCRIPTION_MAX_CHARS = 2000

# Allowed enum sets, used to clamp Claude's output to safe values. If the
# model hallucinates a category, we fall back to "Other" / "Unspecified"
# rather than writing garbage into the column.
FUNCTION_CATEGORIES = {
    "Community", "Design", "Engineering", "Marketing",
    "Operations", "Sales", "BizDev", "Product", "Other",
}
SENIORITIES = {"Junior", "Mid", "Senior", "Lead", "Head", "Executive", "Unspecified"}
VERTICALS = {
    "DeFi", "L1", "L2", "CEX", "DEX", "Gaming",
    "Infrastructure", "NFT", "RWA", "Oracles", "AI-Crypto", "Other",
}
REMOTE_STATUSES = {"Remote", "Hybrid", "Onsite", "Unspecified"}


def _fetch_unclassified_jobs(client, limit: int) -> list[dict]:
    """Jobs with function_category NULL AND score_total >= CLASSIFY_MIN_SCORE
    AND is_active=true — i.e. only jobs that could plausibly reach cv_score.

    Cold jobs stay unclassified on purpose: their function_category is
    never read by the warm-only UI views, and skipping them here drops
    classify cost on the long tail (low-score aggregator postings).

    We also select salary_source so we don't overwrite a scraper-listed
    salary with a later AI-extracted one.
    """
    if client is None:
        return []
    try:
        resp = (
            client.table("jobs")
            .select("id,title,company,location,description,salary_source")
            .is_("function_category", "null")
            .eq("is_active", True)
            .gte("score_total", CLASSIFY_MIN_SCORE)
            .limit(limit)
            .execute()
        )
        return getattr(resp, "data", []) or []
    except Exception as e:
        print(f"  [supabase] fetch unclassified failed: {e}", file=sys.stderr)
        return []


def _build_user_message(job: dict) -> str:
    desc = (job.get("description") or "").strip()[:DESCRIPTION_MAX_CHARS]
    return USER_TEMPLATE.format(
        title=(job.get("title") or "")[:300],
        company=(job.get("company") or "") or "Unknown",
        location=(job.get("location") or "") or "Unspecified",
        description=desc or "(no description available)",
    )


def _build_batch_requests(jobs: list[dict]) -> list[dict]:
    """Build Batch API request dicts — one per job, custom_id=job.id."""
    out = []
    for job in jobs:
        out.append({
            "custom_id": str(job["id"]),
            "params": {
                "model": MODEL,
                "max_tokens": 300,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": _build_user_message(job)}
                ],
            },
        })
    return out


def _submit_batch(anthropic_client, requests: list[dict]):
    """Submit to Batch API. Returns the batch object or None."""
    try:
        return anthropic_client.messages.batches.create(requests=requests)
    except Exception as e:
        print(f"  [anthropic] batch create failed: {e}", file=sys.stderr)
        return None


def _clamp_to_enum(value, allowed: set[str], fallback: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return fallback


def _clamp_int_or_none(value) -> int | None:
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n <= 0 or n > 10_000_000:
        return None
    return n


def _clamp_confidence(value) -> float | None:
    if value is None:
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        n = 0.0
    if n > 1:
        n = 1.0
    return round(n, 2)


def _parsed_to_row(parsed: dict, job: dict) -> dict:
    """Turn Claude's JSON into a jobs-table update patch.

    Only touches salary fields if the scraper didn't already find a listed
    one — AI extraction is the fallback, not the override.
    """
    fields = {
        "function_category": _clamp_to_enum(
            parsed.get("function_category"), FUNCTION_CATEGORIES, "Other"
        ),
        "function_confidence": _clamp_confidence(parsed.get("function_confidence")),
        "seniority": _clamp_to_enum(parsed.get("seniority"), SENIORITIES, "Unspecified"),
        "vertical": _clamp_to_enum(parsed.get("vertical"), VERTICALS, "Other"),
        "remote_status": _clamp_to_enum(
            parsed.get("remote_status"), REMOTE_STATUSES, "Unspecified"
        ),
    }
    if job.get("salary_source") != "listed":
        salary_min = _clamp_int_or_none(parsed.get("salary_min_usd"))
        salary_max = _clamp_int_or_none(parsed.get("salary_max_usd"))
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            salary_min, salary_max = salary_max, salary_min
        if salary_min is not None or salary_max is not None:
            fields["salary_min_usd"] = salary_min
            fields["salary_max_usd"] = salary_max
            fields["salary_source"] = "extracted_by_ai"
    return fields


def _write_back(client, updates: list[tuple[str, dict]]) -> int:
    """updates = list of (job_id, patch_dict). Returns rows updated."""
    if client is None:
        return 0
    written = 0
    for job_id, patch in updates:
        try:
            resp = client.table("jobs").update(patch).eq("id", job_id).execute()
            if getattr(resp, "data", None):
                written += 1
        except Exception as e:
            print(f"  [supabase] update {job_id} failed: {e}", file=sys.stderr)
    return written


def _compute_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK +
        (output_tokens / 1_000_000) * BATCH_OUTPUT_PER_MTOK,
        6,
    )


def _log_spend(
    client,
    *,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    notes: str,
) -> None:
    if client is None:
        return
    row = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "operation": "classify",
        "model": MODEL,
        "input_tokens": input_tokens,
        "cached_input_tokens": 0,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "notes": notes[:500],
    }
    try:
        client.table("spend_tracking").insert(row).execute()
    except Exception as e:
        print(f"  [supabase] spend_tracking insert failed: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify unclassified jobs via Haiku 4.5 Batch API.")
    ap.add_argument("--limit", type=int, default=MAX_JOBS_PER_RUN,
                    help=f"cap per run (default {MAX_JOBS_PER_RUN})")
    ap.add_argument("--dry", action="store_true",
                    help="don't call Anthropic, don't write back")
    args = ap.parse_args()

    print(
        f"classify — started={datetime.now(timezone.utc).isoformat()}  "
        f"limit={args.limit}  dry={args.dry}"
    )

    sb = supabase_client.get_client()
    if sb is None and not args.dry:
        print("  [fatal] no Supabase client — set SUPABASE_URL + SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    # Kill switch first — before we fetch, before we build prompts.
    try:
        budget.assert_under_budget(sb, operation="classify")
    except budget.BudgetExceeded as e:
        print(f"  [kill-switch] {e}", file=sys.stderr)
        return 3

    jobs = _fetch_unclassified_jobs(sb, args.limit) if sb else []
    if not jobs:
        print("  nothing to classify (function_category IS NULL → 0 rows)")
        return 0
    print(f"  {len(jobs)} jobs to classify")

    if args.dry:
        print(f"\n  [dry] sample request for job id {jobs[0]['id']}:")
        print("---")
        print(_build_user_message(jobs[0])[:800])
        print("---")
        print(f"  [dry] would submit {len(jobs)} requests to Batch API")
        return 0

    anthropic = _get_anthropic_client()
    if anthropic is None:
        return 2

    payload = _build_batch_requests(jobs)
    batch = _submit_batch(anthropic, payload)
    if batch is None:
        return 4
    batch_id = batch.id
    print(f"  [anthropic] batch submitted: {batch_id}")

    final = _poll_batch(anthropic, batch_id)
    if final is None:
        print("  [anthropic] batch never ended — aborting write-back", file=sys.stderr)
        return 4

    # Stream results. Results are not guaranteed ordered; we rely on custom_id.
    input_tokens_total = 0
    output_tokens_total = 0
    updates: list[tuple[str, dict]] = []
    job_by_id = {str(j["id"]): j for j in jobs}
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
            output_tokens_total += getattr(usage, "output_tokens", 0) or 0
        # Content is a list of blocks — grab the first text block.
        text = ""
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                break
        parsed = _extract_json(text)
        if not parsed:
            parse_failed += 1
            continue
        job = job_by_id.get(custom_id)
        if job is None:
            parse_failed += 1
            continue
        updates.append((custom_id, _parsed_to_row(parsed, job)))
        ok += 1

    print(
        f"  [parse] ok={ok}  parse_failed={parse_failed}  errored={errored}  "
        f"input_tokens={input_tokens_total}  output_tokens={output_tokens_total}"
    )

    written = _write_back(sb, updates)
    cost = _compute_cost(input_tokens_total, output_tokens_total)
    print(f"  [writeback] {written}/{len(updates)} rows updated  cost=${cost}")

    _log_spend(
        sb,
        input_tokens=input_tokens_total,
        output_tokens=output_tokens_total,
        cost_usd=cost,
        notes=(
            f"batch_id={batch_id} jobs={len(jobs)} "
            f"ok={ok} parse_failed={parse_failed} errored={errored}"
        ),
    )

    print(f"done: {datetime.now(timezone.utc).isoformat()}")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
