"""Spend cap enforcement — Phase 3.

Reads month-to-date sum of `spend_tracking.cost_usd`. Raises BudgetExceeded
if MTD has already hit the cap. This is the kill switch that stops a
runaway loop (retry hell, infinite Batch resubmits, classifier in a loop,
etc.) from draining the $10 ceiling.

Per §D4: hard kill at $8 MTD. Alert email on trip (wired up in Phase 9).

Used by classify.py, cv_score.py, and weekly_summary.py — call
`assert_under_budget(client)` at the top of main() before spending anything.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

# §D4: hard kill at $8 MTD. Sits well under the $10 ceiling so we have
# slack for the Resend alert email + any retries the scheduler fires
# between the trip and us noticing.
BUDGET_CAP_USD = 8.00


class BudgetExceeded(RuntimeError):
    """Raised when month-to-date spend has already exceeded the cap."""


def _month_start_iso() -> str:
    """Start of the current UTC month — spend resets at this boundary."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc).isoformat()


def month_to_date_spend(client) -> float:
    """Return sum(cost_usd) for rows run_at >= start of current UTC month.

    Fail-soft: if the query fails (Supabase outage, etc.), we log and
    return 0.0 so the run proceeds. Better to risk a tiny bit of spend
    than to silently stall classification because Supabase hiccuped.
    """
    if client is None:
        return 0.0
    try:
        resp = (
            client.table("spend_tracking")
            .select("cost_usd")
            .gte("run_at", _month_start_iso())
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        return round(sum(float(r.get("cost_usd") or 0) for r in rows), 6)
    except Exception as e:
        print(f"  [budget] month_to_date_spend failed (treating as 0): {e}", file=sys.stderr)
        return 0.0


def assert_under_budget(client, cap_usd: float = BUDGET_CAP_USD) -> float:
    """Raise BudgetExceeded if MTD >= cap. Return the MTD total on success."""
    spent = month_to_date_spend(client)
    print(f"  [budget] MTD spend=${spent:.4f}  cap=${cap_usd:.2f}")
    if spent >= cap_usd:
        raise BudgetExceeded(
            f"MTD spend ${spent:.4f} >= cap ${cap_usd:.2f} — refusing to run"
        )
    return spent
