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

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# §D4: hard kill at $8 MTD. Sits well under the $10 ceiling so we have
# slack for the Resend alert email + any retries the scheduler fires
# between the trip and us noticing.
BUDGET_CAP_USD = 8.00

ALERT_RECIPIENT = "eugeniogdelatorre@gmail.com"
ALERT_FROM = os.environ.get("RESEND_FROM") or "Job Agent <onboarding@resend.dev>"


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


def _send_cap_alert(spent: float, cap_usd: float, operation: str | None) -> None:
    """Best-effort Resend email when the cap trips.

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
    subject = f"[job-agent] Budget cap tripped — paused at ${spent:.4f}"
    html = (
        '<div style="font-family:system-ui,sans-serif;padding:20px;max-width:560px">'
        "<h2>Spend cap tripped</h2>"
        f"<p>Month-to-date AI spend has hit <strong>${spent:.4f}</strong> "
        f"(cap ${cap_usd:.2f}). Workflow <code>{op}</code> refused to run.</p>"
        "<p>Check <code>/settings</code> to see which operation is burning budget, "
        "and inspect recent rows in <code>spend_tracking</code>.</p>"
        "<p>The cap resets on the 1st of next UTC month. To resume sooner, delete "
        "rows from <code>spend_tracking</code> for the current month (pragmatic "
        "fallback) or raise <code>BUDGET_CAP_USD</code>.</p>"
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
    """Raise BudgetExceeded if MTD >= cap. Return the MTD total on success.

    Also sends a one-shot Resend alert email on the trip (best-effort).
    Pass ``operation`` (e.g. "classify" / "cv_score") so the alert tells
    Eugenio which workflow refused to run.
    """
    spent = month_to_date_spend(client)
    print(f"  [budget] MTD spend=${spent:.4f}  cap=${cap_usd:.2f}")
    if spent >= cap_usd:
        _send_cap_alert(spent, cap_usd, operation)
        raise BudgetExceeded(
            f"MTD spend ${spent:.4f} >= cap ${cap_usd:.2f} — refusing to run"
        )
    return spent
