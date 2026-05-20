"""C3 (REVIEW.md, 2026-05-19): kill-switch must fail CLOSED on Supabase errors.

The docstring of ``month_to_date_spend`` promises fail-closed (+inf) but the
bare ``except Exception`` at the bottom returned ``0.0``, which made
``assert_under_budget`` silently pass even when the spend query had blown
up. This test pins the contract so the polarity can't flip back.
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

from scraper import budget


def test_month_to_date_spend_fails_closed_on_supabase_error():
    client = MagicMock()
    client.table.return_value.select.return_value.gte.return_value.range.return_value.execute.side_effect \
        = RuntimeError("PostgREST 503")
    result = budget.month_to_date_spend(client)
    assert math.isinf(result), \
        "Supabase exceptions must fail CLOSED (return +inf) so the kill switch trips"


def test_assert_under_budget_raises_when_query_errors():
    client = MagicMock()
    # Cover both the no-operation chain (.gte().range().execute()) and the
    # with-operation chain (.gte().eq().range().execute()) so both code paths
    # inside month_to_date_spend hit the exception.
    client.table.return_value.select.return_value.gte.return_value.range.return_value.execute.side_effect \
        = RuntimeError("PostgREST 503")
    client.table.return_value.select.return_value.gte.return_value.eq.return_value.range.return_value.execute.side_effect \
        = RuntimeError("PostgREST 503")
    try:
        budget.assert_under_budget(client, operation="cv_score")
    except budget.BudgetExceeded:
        return
    raise AssertionError("BudgetExceeded was not raised despite a Supabase error")
