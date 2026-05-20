"""H5 (REVIEW.md, 2026-05-20): cv_extract.extract_skill_graph makes a
real-time Anthropic API call without first checking the global budget.
Because cv_extract is called lazily from inside cv_score (after the
cv_score budget check), and because it may also be called directly, it
must verify the global cap itself before spending.

Fix: call budget.assert_under_budget(supabase_client) inside
extract_skill_graph before the anthropic.messages.create call.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from scraper import cv_extract, budget


def test_extract_skill_graph_raises_when_global_budget_exceeded():
    """extract_skill_graph must raise BudgetExceeded (not call the API)
    when the global spend cap has already been hit."""
    anthropic_client = MagicMock()
    supabase_client  = MagicMock()

    with patch.object(budget, "assert_under_budget", side_effect=budget.BudgetExceeded("cap hit")):
        with pytest.raises(budget.BudgetExceeded):
            cv_extract.extract_skill_graph(anthropic_client, "some resume text", supabase_client)

    # Must NOT have called the Anthropic API
    anthropic_client.messages.create.assert_not_called()


def test_extract_skill_graph_checks_budget_before_api_call():
    """assert_under_budget must be invoked before messages.create."""
    call_order: list[str] = []

    anthropic_client = MagicMock()
    supabase_client  = MagicMock()

    def fake_assert(*a, **kw):
        call_order.append("budget_check")

    def fake_create(*a, **kw):
        call_order.append("api_call")
        msg = MagicMock()
        msg.usage = MagicMock(input_tokens=100, output_tokens=20)
        # Return a content block with valid JSON
        block = MagicMock()
        block.type = "text"
        block.text = '{"skills": [], "seniority": "mid", "languages": [], "deal_breakers": [], "preferences": []}'
        msg.content = [block]
        return msg

    with patch.object(budget, "assert_under_budget", side_effect=fake_assert):
        anthropic_client.messages.create.side_effect = fake_create
        cv_extract.extract_skill_graph(anthropic_client, "some resume text", supabase_client)

    assert call_order[0] == "budget_check", (
        "assert_under_budget must be called BEFORE the Anthropic API call"
    )
    assert "api_call" in call_order


def test_extract_skill_graph_skips_budget_when_no_supabase_client():
    """When supabase_client is None (dry run), budget check is skipped
    gracefully (no client → no spend_tracking → no check possible)."""
    anthropic_client = MagicMock()
    msg = MagicMock()
    msg.usage = MagicMock(input_tokens=50, output_tokens=10)
    block = MagicMock()
    block.type = "text"
    block.text = '{"skills": [], "seniority": "mid", "languages": [], "deal_breakers": [], "preferences": []}'
    msg.content = [block]
    anthropic_client.messages.create.return_value = msg

    # Should not raise even with no supabase client
    result = cv_extract.extract_skill_graph(anthropic_client, "resume text", supabase_client=None)
    # Result may be None (JSON parse path) or a dict — either is fine; no exception is the contract
