"""H1 (REVIEW.md, 2026-05-20): _send_cap_alert is called on every run
after the budget trips — no de-dup. By end-of-month that's 25+ identical
emails plus Resend free-tier consumption.

Fix:
  _alert_already_sent(client, scope, operation) → bool
      Queries spend_alerts for an existing row matching (month_start,
      scope, operation). Returns False on any error — fail-OPEN so a DB
      hiccup doesn't block the FIRST trip email.
  _mark_alert_sent(client, scope, operation)
      Inserts a row after a successful send.
  _send_cap_alert modified to call these two helpers.

Migration: spend_alerts table with unique index on (month_start, scope,
operation) applied separately via Supabase MCP.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

from scraper import budget


# ────────────────────────────── _alert_already_sent ──────────────────────────

def test_alert_already_sent_returns_false_when_no_row():
    """Returns False when no existing alert row is found."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    result = budget._alert_already_sent(client, scope="stage", operation="cv_score")
    assert result is False


def test_alert_already_sent_returns_true_when_row_exists():
    """Returns True when an existing alert row for this month is found."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": 1}])
    result = budget._alert_already_sent(client, scope="stage", operation="cv_score")
    assert result is True


def test_alert_already_sent_fails_open_on_exception():
    """Returns False (fail-OPEN) when the Supabase query raises. Missing
    a duplicate is annoying; missing the FIRST alert is operationally worse."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = RuntimeError("DB down")
    result = budget._alert_already_sent(client, scope="global", operation=None)
    assert result is False


def test_alert_already_sent_returns_false_when_client_none():
    result = budget._alert_already_sent(None, scope="stage", operation="classify")
    assert result is False


# ────────────────────────────── send de-dup integration ──────────────────────

def _make_client_with_alert_states(*alert_exists_sequence):
    """Return a MagicMock client whose spend_alerts SELECT returns the
    given sequence of data lists on successive calls."""
    client = MagicMock()
    execute_mock = client.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute
    execute_mock.side_effect = [
        MagicMock(data=data) for data in alert_exists_sequence
    ]
    return client


@patch.object(budget, "_send_cap_alert")
def test_second_budget_trip_does_not_resend_email(send_mock):
    """_send_cap_alert must be called at most once per (month, scope, op)."""
    # First trip: no existing alert row → email sent, row inserted
    # Second trip: row exists → email suppressed
    client = _make_client_with_alert_states(
        [],           # first _alert_already_sent → no row
        [{"id": 1}],  # second _alert_already_sent → row exists
    )
    with patch.object(budget, "month_to_date_spend", return_value=999.0):
        for _ in range(2):
            try:
                budget.assert_under_budget(client, operation="cv_score")
            except budget.BudgetExceeded:
                pass

    assert send_mock.call_count == 1, (
        "Cap-trip email must be sent at most once per (month, scope, operation). "
        f"Got {send_mock.call_count} calls."
    )


@patch.object(budget, "_send_cap_alert")
def test_first_budget_trip_does_send_email(send_mock):
    """The very first trip for this (month, scope, op) must always send."""
    client = _make_client_with_alert_states(
        [],  # no existing row → send
        [],  # global check also no row
    )
    with patch.object(budget, "month_to_date_spend", return_value=999.0):
        try:
            budget.assert_under_budget(client, operation="cv_score")
        except budget.BudgetExceeded:
            pass

    assert send_mock.call_count >= 1
