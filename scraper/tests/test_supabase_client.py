"""Tests for supabase_client fetch_suspended_sources and update_source_state."""
from unittest.mock import MagicMock, call

import scraper.supabase_client as sc
from scraper.supabase_client import fetch_suspended_sources, update_source_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_select_client(data, *, rpc_raises_missing: bool = True):
    """Return a mock Supabase client.

    By default ``client.rpc(...).execute()`` raises a "function not found"
    error so update_source_state falls through to the legacy read-modify-
    write path the tests inspect. Pass ``rpc_raises_missing=False`` to
    exercise the RPC happy path.
    """
    client = MagicMock()
    resp = MagicMock()
    resp.data = data
    # fetch_suspended_sources chain: .table().select().eq().execute()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = resp
    # update_source_state SELECT chain: .table().select().eq().maybe_single().execute()
    client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = resp
    # upsert chain (return value doesn't matter much)
    client.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    if rpc_raises_missing:
        # Simulate the bump_source_state RPC not being deployed yet.
        # Production code falls through to the legacy upsert path.
        client.rpc.return_value.execute.side_effect = Exception(
            "Could not find the function public.bump_source_state in the schema cache "
            "(PGRST202)"
        )
    else:
        client.rpc.return_value.execute.return_value = MagicMock()
    return client


def _reset_rpc_warn_flag():
    """Tests run in arbitrary order; reset the one-shot warning so the
    'rpc missing' message is observed exactly when the test expects."""
    sc._RPC_MISSING_WARNED = False


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
    """On failure, consecutive_failures is incremented; suspended stays False below threshold."""
    existing = {"consecutive_failures": 2, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_y", success=False)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]
    assert row["consecutive_failures"] == 3
    assert row["suspended"] is False
    assert row["source_name"] == "src_y"


def test_update_below_threshold_does_not_suspend():
    """5th and 6th consecutive failures stay un-suspended (threshold is 7)."""
    existing = {"consecutive_failures": 5, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_z", success=False)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]
    assert row["consecutive_failures"] == 6
    assert row["suspended"] is False


def test_update_7th_failure_suspends():
    """On the 7th consecutive failure (= one full week of daily scrapes), suspended is set to True."""
    existing = {"consecutive_failures": 6, "suspended": False}
    client = _make_select_client(existing)

    update_source_state(client, "src_z", success=False)

    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None, "upsert was never called"
    row = upsert_call[0][0]
    assert row["consecutive_failures"] == 7
    assert row["suspended"] is True
    assert row["source_name"] == "src_z"


def test_update_new_source_first_failure():
    """When no prior row exists, first failure creates row with consecutive_failures=1."""
    _reset_rpc_warn_flag()
    client = _make_select_client(None)  # data=None simulates no existing row
    update_source_state(client, "brand_new_source", success=False)
    row = client.table.return_value.upsert.call_args[0][0]
    assert row["consecutive_failures"] == 1
    assert row["suspended"] is False
    assert row["source_name"] == "brand_new_source"


# ---------------------------------------------------------------------------
# RPC happy path (audit N-H2 / N-M4)
# ---------------------------------------------------------------------------

def test_update_uses_rpc_when_available():
    """When the bump_source_state RPC is deployed, update_source_state
    calls it and does NOT fall back to the legacy upsert path."""
    _reset_rpc_warn_flag()
    client = _make_select_client({"consecutive_failures": 2, "suspended": False},
                                  rpc_raises_missing=False)
    update_source_state(client, "src_rpc", success=False)

    # RPC was called with the expected payload.
    rpc_call = client.rpc.call_args
    assert rpc_call is not None, "rpc was never called"
    assert rpc_call[0][0] == "bump_source_state"
    args = rpc_call[0][1]
    assert args["p_source_name"] == "src_rpc"
    assert args["p_success"] is False
    assert isinstance(args["p_suspend_threshold"], int)

    # Legacy upsert path was NOT exercised.
    assert client.table.return_value.upsert.call_args is None, \
        "upsert path should be skipped when RPC succeeds"


def test_update_falls_back_when_rpc_missing():
    """If the RPC isn't deployed yet, fallback to legacy upsert still works."""
    _reset_rpc_warn_flag()
    client = _make_select_client({"consecutive_failures": 0, "suspended": False})
    update_source_state(client, "src_legacy", success=False)
    # RPC was attempted...
    assert client.rpc.call_args is not None
    # ...and the legacy upsert ran as fallback.
    upsert_call = client.table.return_value.upsert.call_args
    assert upsert_call is not None
    assert upsert_call[0][0]["consecutive_failures"] == 1
