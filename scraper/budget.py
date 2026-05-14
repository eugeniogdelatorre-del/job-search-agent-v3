"""Spend cap enforcement — Phase 3.

Reads month-to-date sum of `spend_tracking.cost_usd`. Raises BudgetExceeded
if MTD has already hit the cap. This is the kill switch that stops a
runaway loop (retry hell, infinite Batch resubmits, classifier in a loop,
etc.) from draining the monthly ceiling.

Per §D4 (revised 2026-05-14): hard kill at $20 MTD. Alert email on trip.

Used by classify.py, cv_score.py, and weekly_summary.py — call
`assert_under_budget(client)` at the top of main() before spending anything.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# §D4: hard kill at $20 MTD (raised from $8 on 2026-05-14, see comment
# block below). Comfortable safety belt against runaway loops while
# tolerating one-off remediation costs.
# 2026-05-14: bumped from $8 → $20 after the dedup-key collision bug
# pushed MTD to $8.43 in a single day (1,829 duplicate rows hit classify
# + geo_filter + cv_score for the same jobs already processed). At the
# operator's projected ~$0.22/month steady-state, $20 is ~90× normal
# usage — still well above anything natural, generous enough to absorb
# one-off remediation runs (rescore, dedup repair) without tripping.
BUDGET_CAP_USD = 20.00

# Per-stage caps (sum = global cap above). When cv_score trips, classify
# and geo_filter keep running so the dashboard stays current with new-job
# classification while CV scoring pauses for the rest of the month —
# this is the most common failure mode (cv_score has the largest
# per-job token cost and the broadest input set).
#
# At projected ~$0.22/month total, current usage sits at roughly
#   classify   ~$0.04   (125× headroom on the $5 cap)
#   geo_filter ~$0.03   (100× headroom on the $3 cap)
#   cv_score   ~$0.15   ( 80× headroom on the $12 cap)
# so a real trip means a clearly broken loop, not natural growth.
# Scaled 2.5× from the original $2/$1/$5 split when the global cap moved
# from $8 to $20 on 2026-05-14, then rounded to friendlier integers.
STAGE_BUDGETS: dict[str, float] = {
    "classify":    5.00,
    "geo_filter":  3.00,
    "cv_score":   12.00,
}

ALERT_RECIPIENT = "eugeniogdelatorre@gmail.com"
ALERT_FROM = os.environ.get("RESEND_FROM") or "Job Agent <onboarding@resend.dev>"


class BudgetExceeded(RuntimeError):
    """Raised when month-to-date spend has already exceeded the cap."""


def _month_start_iso() -> str:
    """Start of the current UTC month — spend resets at this boundary."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()


# PostgREST's default max-rows ceiling (commonly 1000) silently truncates
# a single unbounded `.select().execute()`. If we ever stop summing the
# tail, the budget kill switch fails *open* and a runaway can blow past
# the $20 ceiling. We paginate through `range()` until either the count
# matches what we've drained or the page returns short, and fail *closed*
# (return +inf so `assert_under_budget` trips) if anything looks off.
_SPEND_PAGE_SIZE = 1000
# 50 × 1000 = 50k rows in a single UTC month. At projected ~$0.22/mo with
# a handful of pipeline runs per day, real volume is in the dozens. Hitting
# this cap means something is broken — fail closed.
#
# Audit M5 (2026-05-14): one row per BATCH (not per job). classify and
# cv_score insert a single spend_tracking row per Anthropic batch, so
# 50k rows ≈ 50k batches. At the current cadence (~10 batches/day max,
# pipeline runs ~once daily plus manual dispatches) that's > 13 years
# of normal operation — comfortable. The cap only matters if a future
# change starts logging per-job rows, in which case raise it explicitly
# (don't quietly lift the page count and hope).
_SPEND_MAX_PAGES = 50


def month_to_date_spend(client, operation: str | None = None) -> float:
    """Return sum(cost_usd) for rows run_at >= start of current UTC month.

    When ``operation`` is given, only that stage's rows are summed (used
    by the per-stage budget caps in STAGE_BUDGETS). When omitted, returns
    the global total across all stages.

    Pages through results so the PostgREST default max-rows ceiling does
    not silently under-count. Fail-soft on transient errors (return 0.0)
    to preserve the original policy: a Supabase hiccup shouldn't stall
    classify/cv_score when actual spend is tiny. Fail-closed (+inf, which
    trips the >= cap check in ``assert_under_budget``) only on the
    specific cases where the query *succeeded* but the result is
    suspicious — paginated past the safety cap, or the exact-count
    returned by Supabase disagrees with what we drained.
    """
    if client is None:
        return 0.0
    try:
        total = 0.0
        rows_fetched = 0
        exact_count: int | None = None
        ran_away = True  # flipped to False on a clean break
        for page in range(_SPEND_MAX_PAGES):
            query = (
                client.table("spend_tracking")
                .select("cost_usd", count="exact")
                .gte("run_at", _month_start_iso())
            )
            if operation is not None:
                query = query.eq("operation", operation)
            resp = (
                query
                .range(page * _SPEND_PAGE_SIZE, (page + 1) * _SPEND_PAGE_SIZE - 1)
                .execute()
            )
            rows = getattr(resp, "data", []) or []
            total += sum(float(r.get("cost_usd") or 0) for r in rows)
            rows_fetched += len(rows)
            exact_count = getattr(resp, "count", None)
            if not rows or len(rows) < _SPEND_PAGE_SIZE:
                ran_away = False
                break
        if ran_away:
            print(
                f"  [budget] paged past {_SPEND_MAX_PAGES * _SPEND_PAGE_SIZE} "
                "rows in spend_tracking this month — refusing to estimate; "
                "treating as over-cap",
                file=sys.stderr,
            )
            return float("inf")
        if exact_count is not None and rows_fetched < exact_count:
            print(
                f"  [budget] drained {rows_fetched} rows but count="
                f"{exact_count}; treating as over-cap to be safe",
                file=sys.stderr,
            )
            return float("inf")
        return round(total, 6)
    except Exception as e:
        print(f"  [budget] month_to_date_spend failed (treating as 0): {e}", file=sys.stderr)
        return 0.0


def _send_cap_alert(spent: float, cap_usd: float, operation: str | None, *, scope: str) -> None:
    """Best-effort Resend email when the cap trips.

    ``scope`` is either ``"stage"`` (only the named stage paused — others
    continue to run) or ``"global"`` (every AI stage paused — total MTD
    spend across all stages exceeded the global ceiling). The wording in
    the email body matches so the operator can tell at a glance whether
    one runaway stage or all of them tripped.

    Fail-soft: any failure here must not prevent the BudgetExceeded
    from propagating. The whole point is to stop spending; we'd rather
    halt silently than crash in the alert path and accidentally let a
    retry sneak through.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("  [budget] RESEND_API_KEY missing; skipping alert email", file=sys.stderr)
        return
    op = operation or "unknown"
    if scope == "stage":
        subject = f"[job-agent] {op} stage budget tripped — paused at ${spent:.4f}"
        body = (
            f"<p>Stage <code>{op}</code> has spent <strong>${spent:.4f}</strong> "
            f"this UTC month (stage cap ${cap_usd:.2f}). It is paused for the "
            "rest of the month; OTHER stages continue to run normally.</p>"
        )
    else:
        subject = f"[job-agent] Global budget tripped — all AI paused at ${spent:.4f}"
        body = (
            f"<p>Total month-to-date AI spend has hit <strong>${spent:.4f}</strong> "
            f"(global cap ${cap_usd:.2f}). Every AI stage is paused for the rest of "
            "the month.</p>"
        )
    html = (
        '<div style="font-family:system-ui,sans-serif;padding:20px;max-width:560px">'
        "<h2>Spend cap tripped</h2>"
        + body +
        "<p>Check <code>/settings</code> to see which operation is burning budget, "
        "and inspect recent rows in <code>spend_tracking</code>.</p>"
        "<p>The cap resets on the 1st of next UTC month. To resume sooner, delete "
        "rows from <code>spend_tracking</code> for the current month (pragmatic "
        "fallback) or raise the stage's entry in <code>STAGE_BUDGETS</code>.</p>"
        "</div>"
    )
    payload = {
        "from": ALERT_FROM,
        "to": [ALERT_RECIPIENT],
        "subject": subject,
        "html": html,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Cloudflare (in front of api.resend.com) 1010-bans the default
            # ``Python-urllib/3.x`` UA. A generic UA passes through fine.
            "User-Agent": "job-search-agent-v3/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"  [budget] alert email sent: {resp.status}")
    except urllib.error.HTTPError as e:
        print(
            f"  [budget] alert email HTTP {e.code}: {e.read()[:300]!r}",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"  [budget] alert email failed: {e}", file=sys.stderr)


def assert_under_budget(
    client, cap_usd: float = BUDGET_CAP_USD, operation: str | None = None
) -> float:
    """Raise BudgetExceeded if MTD spend has tripped a cap. Return the
    stage's MTD total on success (or the global total if no stage cap
    applies to this operation).

    Two checks, in order:
      1. PER-STAGE — if ``operation`` is in ``STAGE_BUDGETS``, the spend
         filtered to that stage is compared to the stage cap. Only that
         stage pauses on trip; other stages keep running.
      2. GLOBAL — total spend across all stages is compared to
         ``cap_usd`` (defaults to ``BUDGET_CAP_USD``). Trip = every AI
         stage paused. Defense-in-depth against a misconfigured
         STAGE_BUDGETS (e.g. all four set to $99 by accident).

    Also sends a one-shot Resend alert email on the trip (best-effort).
    Pass ``operation`` so the alert tells Eugenio which workflow refused
    to run, and so the per-stage check can apply.
    """
    # --- per-stage gate ---
    stage_cap = STAGE_BUDGETS.get(operation or "")
    if stage_cap is not None:
        stage_spent = month_to_date_spend(client, operation=operation)
        print(
            f"  [budget] stage={operation} MTD=${stage_spent:.4f}  "
            f"stage_cap=${stage_cap:.2f}"
        )
        if stage_spent >= stage_cap:
            _send_cap_alert(stage_spent, stage_cap, operation, scope="stage")
            raise BudgetExceeded(
                f"Stage '{operation}' MTD spend ${stage_spent:.4f} >= "
                f"stage cap ${stage_cap:.2f} — refusing to run (other stages "
                "continue)"
            )

    # --- global backstop ---
    spent = month_to_date_spend(client)
    print(f"  [budget] global MTD spend=${spent:.4f}  global_cap=${cap_usd:.2f}")
    if spent >= cap_usd:
        _send_cap_alert(spent, cap_usd, operation, scope="global")
        raise BudgetExceeded(
            f"Global MTD spend ${spent:.4f} >= cap ${cap_usd:.2f} — refusing to run"
        )
    # Return the stage-specific spend when relevant (more actionable for
    # callers); otherwise the global total.
    return month_to_date_spend(client, operation=operation) if stage_cap is not None else spent
