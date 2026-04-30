"""Geo-filter — Phase 2.5 (runs between scrape and cv_score).

Reads the active CV to extract the candidate's city/country, then uses
Claude Haiku 4.5 via the Batch API to decide whether each unfiltered job
is location-accessible for that candidate. Jobs that fail the check are
marked is_active=false and geo_filtered=true so they never reach cv_score.

Rules applied by the AI (same logic as the old rule-based gates, but
now handled by the model so it understands nuance):

  PASS  — fully remote (global, worldwide, anywhere)
  PASS  — remote explicitly open to candidate's country/region
  PASS  — hybrid or on-site in the candidate's exact city
  PASS  — location unspecified / unknown
  FAIL  — on-site or hybrid outside candidate's city
  FAIL  — remote restricted to a country/region that excludes candidate

Columns used (must exist on the `jobs` table):
  geo_filtered   boolean  DEFAULT false   — true once this script has processed the job
  is_active      boolean                  — set false when geo rejects

Pipeline:
    1. budget.assert_under_budget()
    2. Fetch active CV → resolve candidate location (env > AI > regex > hardcoded)
    3. SELECT unfiltered jobs (geo_filtered IS false AND is_active = true
       AND remote_status IS NOT NULL — defer until classify has run)
    4. Build one Batch request per job
    5. Submit, poll, parse
    6. Mark failing jobs: is_active=false, geo_filtered=true, geo_reject_reason=<AI reason>
    7. Mark passing jobs: geo_filtered=true (is_active stays true)
    8. Log spend

Usage:
    python scraper/geo_filter.py            # production run
    python scraper/geo_filter.py --limit 50
    python scraper/geo_filter.py --dry      # build prompts, no AI call, no writes
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

MODEL = "claude-haiku-4-5-20251001"

# Batch API = 50% of base rates. Haiku 4.5: $0.50/$2.50 per MTok in/out.
BATCH_INPUT_PER_MTOK = 0.50
BATCH_OUTPUT_PER_MTOK = 2.50

MAX_JOBS_PER_RUN = 1000   # geo filter is cheap — process everything in one shot
POLL_INTERVAL_SECONDS = 30
POLL_MAX_SECONDS = 25 * 60

DESCRIPTION_MAX_CHARS = 800   # location signal is in the first few lines

# LOCKED system prompt.
SYSTEM_PROMPT = """\
You are a strict location eligibility checker for job postings.
Given a candidate location and a job posting, decide whether the candidate
can legally work this job from their current location.
Return JSON only — no prose, no code fences.
"""

# LOCKED user template — {candidate_location} injected once per batch build.
USER_TEMPLATE = """\
Candidate location: {candidate_location}

Job:
  Title: {title}
  Company: {company}
  Posted location: {location}
  Remote status (AI-classified): {remote_status}
  Description snippet: {description}

Return exactly:
{{"eligible": true_or_false, "reason": "one short sentence"}}

Rules (apply in order, first match wins):
1. Location field is empty/null/unknown → eligible=true
2. Remote status is "Remote" with NO geographic restriction in description → eligible=true
3. Remote status is "Remote" but description restricts to a country/region/timezone
   that EXCLUDES the candidate's country → eligible=false
4. Remote status is "Remote" and restriction INCLUDES candidate's country/region → eligible=true
5. Remote status is "Hybrid" or "Onsite" AND city matches candidate's city → eligible=true
6. Remote status is "Hybrid" or "Onsite" in a different city → eligible=false
7. Remote status "Unspecified": if no location constraint found → eligible=true; else apply rules 3-6
"""


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
            .select("id,parsed_text")
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
        return getattr(resp, "data", None)
    except Exception as e:
        print(f"  [supabase] fetch active resume failed: {e}", file=sys.stderr)
        return None


def _ai_extract_candidate_location(anthropic_client, resume_text: str) -> str | None:
    """Ask Haiku to pull the candidate's residence city/country from the CV.

    One non-batch call per geo_filter run (~$0.0005). Far more reliable than
    the regex fallback, especially for CVs that don't put the city on its
    own line (LinkedIn-style headers, multi-line addresses, etc).
    """
    if anthropic_client is None or not resume_text:
        return None
    snippet = resume_text[:3000]
    try:
        msg = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=40,
            system=(
                "You extract the candidate's current residence location from a resume. "
                "Reply with ONLY a 'City, Country' string (no quotes, no prose, no 'Location:' prefix). "
                "If you cannot determine it with high confidence, reply exactly: Unknown"
            ),
            messages=[{"role": "user", "content": snippet}],
        )
    except Exception as e:
        print(f"  [anthropic] CV location extraction failed: {e}", file=sys.stderr)
        return None

    text = ""
    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = (getattr(block, "text", "") or "").strip()
            break
    text = text.strip().strip('"').strip("'").rstrip(".").strip()
    if not text or text.lower() == "unknown" or len(text) < 3 or len(text) > 100:
        return None
    return text


def _regex_extract_candidate_location(resume_text: str) -> str | None:
    """Last-resort regex extractor — kept for the case where the AI is unreachable."""
    if not resume_text:
        return None
    lines = resume_text.splitlines()
    loc_re = re.compile(
        r"\b(Buenos Aires|Rosario|Córdoba|Mendoza|Argentina|CABA|"
        r"[A-Z][a-z]+,\s*[A-Z][a-zA-Z ]+)\b"
    )
    for line in lines[:30]:
        m = loc_re.search(line)
        if m:
            return m.group(0).strip()
    for line in lines[:30]:
        m = re.search(r"([A-Z][a-zA-Z ]{2,}),\s*([A-Z][a-zA-Z ]{2,})", line)
        if m:
            return m.group(0).strip()
    return None


def _resolve_candidate_location(anthropic_client, resume_text: str) -> str:
    """Resolution order:
        1. CANDIDATE_LOCATION env var (testing / CI override)
        2. AI extraction from the active CV
        3. Regex extraction from the active CV (offline fallback)
        4. Hardcoded "Buenos Aires, Argentina"
    """
    override = (os.environ.get("CANDIDATE_LOCATION") or "").strip()
    if override:
        return override
    ai = _ai_extract_candidate_location(anthropic_client, resume_text)
    if ai:
        return ai
    rx = _regex_extract_candidate_location(resume_text)
    if rx:
        return rx
    return "Buenos Aires, Argentina"


def _fetch_unfiltered_jobs(client, limit: int) -> list[dict]:
    """Jobs not yet geo-filtered AND already classified.

    The `remote_status IS NOT NULL` guard avoids a daily race where this
    job runs at 06:00 UTC before classify (05:00) has finished its batch.
    Unclassified rows would otherwise hit the AI prompt with remote_status
    rendered as 'Unspecified', triggering rule 7 and silently failing open.
    Better to defer them by one cron cycle.
    """
    if client is None:
        return []
    try:
        resp = (
            client.table("jobs")
            .select("id,title,company,location,description,remote_status")
            .eq("is_active", True)
            .eq("geo_filtered", False)
            .not_("remote_status", "is", "null")
            .limit(limit)
            .execute()
        )
        return getattr(resp, "data", []) or []
    except Exception as e:
        print(f"  [supabase] fetch unfiltered jobs failed: {e}", file=sys.stderr)
        return []


def _build_user_message(job: dict, candidate_location: str) -> str:
    desc = (job.get("description") or "").strip()[:DESCRIPTION_MAX_CHARS]
    return USER_TEMPLATE.format(
        candidate_location=candidate_location,
        title=(job.get("title") or "")[:200],
        company=(job.get("company") or "Unknown"),
        location=(job.get("location") or "Unspecified"),
        remote_status=(job.get("remote_status") or "Unspecified"),
        description=desc or "(no description available)",
    )


def _build_batch_requests(jobs: list[dict], candidate_location: str) -> list[dict]:
    out = []
    for job in jobs:
        out.append({
            "custom_id": str(job["id"]),
            "params": {
                "model": MODEL,
                "max_tokens": 120,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": _build_user_message(job, candidate_location)}
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
    print("  [poll] timed out — next run will retry", file=sys.stderr)
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


def _mark_jobs(
    client,
    pass_ids: list[str],
    fail_records: list[tuple[str, str]],
) -> tuple[int, int]:
    """Update DB. fail_records is a list of (job_id, reason) so we keep the
    AI-provided per-job rejection reason in geo_reject_reason."""
    if client is None:
        return (0, 0)
    passed = 0
    failed = 0

    # Process in batches of 100 IDs to stay within URL length limits.
    def _chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    for chunk in _chunks(pass_ids, 100):
        try:
            resp = (
                client.table("jobs")
                .update({"geo_filtered": True})
                .in_("id", chunk)
                .execute()
            )
            passed += len(getattr(resp, "data", None) or chunk)
        except Exception as e:
            print(f"  [supabase] mark-pass failed: {e}", file=sys.stderr)

    # Bucket fails by reason so identical reasons share one chunked update.
    by_reason: dict[str, list[str]] = {}
    for jid, reason in fail_records:
        by_reason.setdefault(reason or "geo_filtered", []).append(jid)
    for reason, ids in by_reason.items():
        for chunk in _chunks(ids, 100):
            try:
                resp = (
                    client.table("jobs")
                    .update({
                        "geo_filtered": True,
                        "is_active": False,
                        "geo_reject_reason": reason,
                    })
                    .in_("id", chunk)
                    .execute()
                )
                failed += len(getattr(resp, "data", None) or chunk)
            except Exception as e:
                print(f"  [supabase] mark-fail failed: {e}", file=sys.stderr)

    return (passed, failed)


def _compute_cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        (input_tokens / 1_000_000) * BATCH_INPUT_PER_MTOK +
        (output_tokens / 1_000_000) * BATCH_OUTPUT_PER_MTOK,
        6,
    )


def _log_spend(client, *, input_tokens: int, output_tokens: int, cost_usd: float, notes: str) -> None:
    if client is None:
        return
    row = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "operation": "geo_filter",
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
    ap = argparse.ArgumentParser(description="AI geo-filter: mark location-ineligible jobs inactive.")
    ap.add_argument("--limit", type=int, default=MAX_JOBS_PER_RUN)
    ap.add_argument("--dry", action="store_true", help="build prompts, no AI call, no writes")
    args = ap.parse_args()

    print(
        f"geo_filter — started={datetime.now(timezone.utc).isoformat()}  "
        f"limit={args.limit}  dry={args.dry}  model={MODEL}"
    )

    sb = supabase_client.get_client()
    if sb is None and not args.dry:
        print("  [fatal] no Supabase client — set SUPABASE_URL + SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 2

    try:
        budget.assert_under_budget(sb, operation="geo_filter")
    except budget.BudgetExceeded as e:
        print(f"  [kill-switch] {e}", file=sys.stderr)
        return 3

    # Init the Anthropic client up-front — we use it both for CV-location
    # extraction and for the per-job batch.
    anthropic = None
    if not args.dry:
        anthropic = _get_anthropic_client()
        if anthropic is None:
            return 2

    # Fetch active CV and resolve the candidate's location:
    #   1. CANDIDATE_LOCATION env override (testing / CI)
    #   2. AI extraction from CV
    #   3. Regex fallback
    #   4. Hard-coded "Buenos Aires, Argentina"
    resume = _fetch_active_resume(sb) if sb else None
    resume_text = (resume.get("parsed_text") or "").strip() if resume else ""
    if not resume:
        print("  [warn] no active resume — will rely on env override or fallback")
    candidate_location = _resolve_candidate_location(anthropic, resume_text)
    print(f"  candidate location: {candidate_location!r}")

    jobs = _fetch_unfiltered_jobs(sb, args.limit) if sb else []
    if not jobs:
        print("  nothing to filter (no jobs with geo_filtered=false AND is_active=true)")
        return 0
    print(f"  {len(jobs)} jobs to geo-filter")

    if args.dry:
        print("\n  [dry] sample prompt:")
        print("---")
        print(_build_user_message(jobs[0], candidate_location)[:600])
        print("---")
        print(f"  [dry] would submit {len(jobs)} requests to Batch API")
        return 0

    payload = _build_batch_requests(jobs, candidate_location)
    batch = _submit_batch(anthropic, payload)
    if batch is None:
        return 4
    batch_id = batch.id
    print(f"  [anthropic] batch submitted: {batch_id}")

    final = _poll_batch(anthropic, batch_id)
    if final is None:
        print("  [anthropic] batch never ended — aborting", file=sys.stderr)
        return 4

    input_tokens_total = 0
    output_tokens_total = 0
    pass_ids: list[str] = []
    fail_records: list[tuple[str, str]] = []
    parse_failed = 0
    errored = 0
    job_ids = {str(j["id"]) for j in jobs}

    for result in anthropic.messages.batches.results(batch_id):
        custom_id = getattr(result, "custom_id", None)
        outcome = getattr(result, "result", None)
        if getattr(outcome, "type", None) != "succeeded":
            errored += 1
            # Fail open: mark geo_filtered=true, keep is_active=true.
            if custom_id and custom_id in job_ids:
                pass_ids.append(custom_id)
            continue
        message = getattr(outcome, "message", None)
        if not message:
            errored += 1
            # Same fail-open contract as the outer error branch.
            if custom_id and custom_id in job_ids:
                pass_ids.append(custom_id)
            continue
        usage = getattr(message, "usage", None)
        if usage:
            input_tokens_total += getattr(usage, "input_tokens", 0) or 0
            output_tokens_total += getattr(usage, "output_tokens", 0) or 0
        text = ""
        for block in getattr(message, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", "") or ""
                break
        parsed = _extract_json(text)
        if not parsed or custom_id not in job_ids:
            parse_failed += 1
            if custom_id and custom_id in job_ids:
                pass_ids.append(custom_id)  # fail open on parse error
            continue
        eligible = parsed.get("eligible")
        if eligible is False:
            reason = str(parsed.get("reason") or "geo_filtered").strip()[:200]
            fail_records.append((custom_id, reason))
        else:
            pass_ids.append(custom_id)

    print(
        f"  [parse] pass={len(pass_ids)}  fail={len(fail_records)}  "
        f"parse_failed={parse_failed}  errored={errored}  "
        f"input_tokens={input_tokens_total}  output_tokens={output_tokens_total}"
    )

    passed_written, failed_written = _mark_jobs(sb, pass_ids, fail_records)
    print(f"  [writeback] {passed_written} passed  {failed_written} geo-rejected")

    cost = _compute_cost(input_tokens_total, output_tokens_total)
    _log_spend(
        sb,
        input_tokens=input_tokens_total,
        output_tokens=output_tokens_total,
        cost_usd=cost,
        notes=(
            f"batch_id={batch_id} candidate={candidate_location!r} "
            f"jobs={len(jobs)} pass={len(pass_ids)} fail={len(fail_records)} "
            f"parse_failed={parse_failed} errored={errored}"
        ),
    )
    print(f"  cost=${cost}  done: {datetime.now(timezone.utc).isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
