"""C2 (REVIEW.md, 2026-05-19): the scraper's "first active resume" lookup
MUST scope by user_id.

Pre-fix, the query was ``.eq("is_active", True).order("id").limit(1)`` with
the service-role client — no user_id filter. With the signup allowlist
widened to three users (Federico, Ana, Eugenio) and a partial unique
index that allows one active resume per user, the next person to activate
a CV could silently start consuming the AI pipeline's spend against their
resume while the weekly digest still shipped to Eugenio.

Option (c) from the audit triage (2026-05-19): single-tenant lock via the
``PIPELINE_OWNER_USER_ID`` env var. These tests pin the contract that:
  1. ``_fetch_active_resume`` filters by user_id when the env var is set, and
  2. the helper returns None (degraded fallback) when the env var is missing
     so main() can fail-closed at the top with a clear error message.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from scraper import supabase_client
from scraper.cv_score import _fetch_active_resume as _cv_score_fetch
from scraper.geo_filter import _fetch_active_resume as _geo_filter_fetch


_OWNER_ID = "00000000-0000-0000-0000-deadbeefcafe"


def _eq_calls(client: MagicMock) -> list[tuple]:
    """Collect all positional .eq(...) call args off the supabase-py chain.

    supabase-py builds the query via attribute chaining; both .select() and
    .eq() return wrappers that themselves expose .eq(). To be robust against
    the order .eq() is called (user_id first vs is_active first), we walk
    both .select.return_value.eq.call_args_list and the next-level .eq.eq...
    """
    select_chain = client.table.return_value.select.return_value
    calls: list[tuple] = list(c.args for c in select_chain.eq.call_args_list)
    # one more level down, in case user_id was the second .eq()
    calls.extend(c.args for c in select_chain.eq.return_value.eq.call_args_list)
    return calls


def test_cv_score_fetch_active_resume_filters_by_owner(monkeypatch):
    monkeypatch.setenv("PIPELINE_OWNER_USER_ID", _OWNER_ID)
    client = MagicMock()
    # Make the chain return an empty result so the function exits cleanly.
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    _cv_score_fetch(client)

    calls = _eq_calls(client)
    assert ("user_id", _OWNER_ID) in calls, (
        f"_fetch_active_resume must scope by user_id; saw eq calls: {calls}"
    )


def test_geo_filter_fetch_active_resume_filters_by_owner(monkeypatch):
    monkeypatch.setenv("PIPELINE_OWNER_USER_ID", _OWNER_ID)
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []

    _geo_filter_fetch(client)

    calls = _eq_calls(client)
    assert ("user_id", _OWNER_ID) in calls, (
        f"_fetch_active_resume must scope by user_id; saw eq calls: {calls}"
    )


def test_fetch_active_resume_returns_none_when_owner_id_missing(monkeypatch):
    """Defensive layer: even if main() forgets the upfront env-var check,
    the helper itself must NOT fall back to a global query that could pick
    up another user's resume. None signals 'no resume found' to callers,
    which they already handle as a fatal."""
    monkeypatch.delenv("PIPELINE_OWNER_USER_ID", raising=False)
    client = MagicMock()
    assert _cv_score_fetch(client) is None
    assert _geo_filter_fetch(client) is None
    # And critically: the query must not have been issued at all (no chance
    # of a service-role-scoped global SELECT firing while the lock is open).
    client.table.assert_not_called()


def test_supabase_client_helper_reads_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_OWNER_USER_ID", _OWNER_ID)
    assert supabase_client.get_pipeline_owner_user_id() == _OWNER_ID
    monkeypatch.delenv("PIPELINE_OWNER_USER_ID")
    assert supabase_client.get_pipeline_owner_user_id() is None
    # Empty string treated as unset (avoids a footgun where GitHub Actions
    # secret-not-set sometimes presents as ""):
    monkeypatch.setenv("PIPELINE_OWNER_USER_ID", "")
    assert supabase_client.get_pipeline_owner_user_id() is None
