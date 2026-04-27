"""Tests for supabase_client fetch_suspended_sources and update_source_state."""
from unittest.mock import MagicMock, call

from scraper.supabase_client import fetch_suspended_sources, update_source_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_select_client(data):
    """Return a mock Supabase client whose SELECT chain returns the given data."""
    client = MagicMock()
    resp = MagicMock()
    resp.data = data
    # fetch_suspended_sources chain: .table().select().eq().execute()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
    # update_source_state SELECT chain: .table().select().eq().maybe_single().execute()
    client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = resp
    # upsert chain (return value doesn't matter much)
    client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    return client


# ---------------------------------------------------------------------------
# fetch_suspended_sources tests
# ---------------------------------------------------------------------------

def test_fetch_suspended_none_client():
    """client=None must return an empty set without any DB calls."""
    result = fetch_suspended_sources(None)
    assert result == set()


def test_fetch_suspended_returns_names():
    """Returns the set of source_name values from the DB response."""
    data = [{"source_name": "src_a"}, {"source_name": "src_b"}]
    client = _make_select_client(data)
    result = fetch_suspended_sources(client)
    assert result == {"src_a", "src_b"}


def test_fetch_suspended_db_error():
    """When .execute() raises, fail-soft returns an empty set."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.execute.side_effect = Exception("db error")
    result = fetch_suspended_sources(client)
    assert result == set()


# ---------------------------------------------------------------------------
# update_source_state tests
# ---------------------------------------------------------------------------

def test_update_none_client():
    """When client is None, function returns immediately without DB calls."""
    # Passing None as the client; if the None-guard is removed,
    # this raises AttributeError on None.table() and the test fails.
    update_source_state(None, "some_source", True)  # must not raise


def test_update_success_resets():
    """On success, upsert row has consecutive_failures=0 and suspended=False."""
    existing = {"consecutive_failures": 3, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_x", success=True)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]  # first positional arg
    assert row["consecutive_failures"] == 0
    assert row["suspended"] is False
    assert row["source_name"] == "src_x"


def test_update_failure_increments():
    """On failure, consecutive_failures is incremented; suspended stays False below 5."""
    existing = {"consecutive_failures": 2, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_y", success=False)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]
    assert row["consecutive_failures"] == 3
    assert row["suspended"] is False
    assert row["source_name"] == "src_y"


def test_update_5th_failure_suspends():
    """On the 5th consecutive failure, suspended is set to True."""
    existing = {"consecutive_failures": 4, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_z", success=False)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]
    assert row["consecutive_failures"] == 5
    assert row["suspended"] is True
    assert row["source_name"] == "src_z"


def test_update_new_source_first_failure():
    """When no prior row exists, first failure creates row with consecutive_failures=1."""
    client = _make_select_client(None)  # data=None simulates no existing row
    update_source_state(client, "brand_new_source", success=False)
    row = client.table.return_value.upsert.call_args[0][0]
    assert row["consecutive_failures"] == 1
    assert row["suspended"] is False
    assert row["source_name"] == "brand_new_source"
