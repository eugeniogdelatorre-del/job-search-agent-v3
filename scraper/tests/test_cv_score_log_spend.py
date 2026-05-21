"""Housekeeping #2 (2026-05-21): cv_score._log_spend must store
cache_write_tokens in its own column (cache_write_input_tokens) instead of
packing them into input_tokens.

Regression: before the fix,
  "input_tokens": input_tokens + cache_write_tokens
caused the input_tokens column to be inflated by cache_write_tokens on every
cv_score run. The cache-read % KPI in SpendChart.tsx produced the same numeric
result (the packing coincidentally preserved the ratio) but the underlying
columns were semantically wrong and unqueryable as separate signals.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from scraper.cv_score import _log_spend


class _FakeTable:
    """Thin stub for supabase_client.table(...).insert(row).execute()."""

    def __init__(self) -> None:
        self.inserted_rows: list[dict] = []

    def insert(self, row: dict) -> "_FakeTable":
        self.inserted_rows.append(row)
        return self

    def execute(self) -> None:
        pass


class _FakeClient:
    def __init__(self, table_stub: _FakeTable) -> None:
        self._table_stub = table_stub

    def table(self, name: str) -> _FakeTable:
        assert name == "spend_tracking"
        return self._table_stub


def _call_log_spend(**overrides) -> dict:
    """Call _log_spend with sensible defaults, return the inserted row."""
    defaults = dict(
        input_tokens=100,
        cache_write_tokens=50,
        cache_read_tokens=200,
        output_tokens=30,
        cost_usd=0.005,
        notes="batch_id=abc resume_id=xyz jobs=5 ok=5 parse_failed=0 errored=0",
    )
    defaults.update(overrides)
    stub = _FakeTable()
    client = _FakeClient(stub)
    _log_spend(client, **defaults)
    assert len(stub.inserted_rows) == 1
    return stub.inserted_rows[0]


# ─── Core unpacking test ────────────────────────────────────────────────────

def test_cache_write_not_packed_into_input_tokens():
    """input_tokens must equal the raw input_tokens arg, not input + cache_write."""
    row = _call_log_spend(input_tokens=100, cache_write_tokens=50)
    assert row["input_tokens"] == 100, (
        f"Expected input_tokens=100 but got {row['input_tokens']}; "
        "cache_write_tokens must be stored in cache_write_input_tokens, not packed here."
    )


def test_cache_write_stored_in_dedicated_column():
    """cache_write_input_tokens column must equal the cache_write_tokens arg."""
    row = _call_log_spend(cache_write_tokens=50)
    assert row.get("cache_write_input_tokens") == 50, (
        f"Expected cache_write_input_tokens=50 but got {row.get('cache_write_input_tokens')}; "
        "the column must be populated."
    )


def test_zero_cache_write_passes_through():
    """Edge case: zero cache_write_tokens must store 0, not be omitted."""
    row = _call_log_spend(cache_write_tokens=0)
    assert row.get("cache_write_input_tokens") == 0


def test_cached_input_tokens_unaffected():
    """cached_input_tokens must equal cache_read_tokens arg exactly."""
    row = _call_log_spend(cache_read_tokens=200)
    assert row["cached_input_tokens"] == 200


def test_notes_not_prefixed_with_cache_write():
    """notes should not carry 'cache_write=...' prefix now that it has a column."""
    row = _call_log_spend(cache_write_tokens=75, notes="batch_id=abc")
    assert not row["notes"].startswith("cache_write="), (
        "notes should no longer start with 'cache_write=…' — that info is in its own column now."
    )


def test_none_client_is_noop():
    """Passing client=None must not raise (fail-soft contract)."""
    _log_spend(
        None,
        input_tokens=100,
        cache_write_tokens=50,
        cache_read_tokens=200,
        output_tokens=30,
        cost_usd=0.005,
        notes="noop",
    )  # should not raise
