"""H3 (REVIEW.md, 2026-05-20): geo_filter.py skips token accounting for
errored Anthropic batch outcomes because the usage block comes AFTER the
``if outcome_type != "succeeded": continue`` guard.

Anthropic bills input tokens on errored requests too (the model received
and processed the prompt before the error). Skipping the usage record
means the spend_tracking MTD sum under-counts geo_filter spend, and the
kill switch fires too late.

Fix: move the usage-accumulation block BEFORE any ``continue`` so it
runs on every result regardless of outcome.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scraper import geo_filter


def _make_errored_result(custom_id: str, input_tokens: int = 500, output_tokens: int = 0):
    """Simulate an Anthropic batch result with type='errored' but non-null message."""
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    message = SimpleNamespace(usage=usage, content=[])
    outcome = SimpleNamespace(type="errored", message=message)
    return SimpleNamespace(custom_id=custom_id, result=outcome)


def _make_succeeded_result(custom_id: str, text: str, input_tokens: int = 300, output_tokens: int = 50):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    content_block = SimpleNamespace(type="text", text=text)
    message = SimpleNamespace(usage=usage, content=[content_block])
    outcome = SimpleNamespace(type="succeeded", message=message)
    return SimpleNamespace(custom_id=custom_id, result=outcome)


def test_errored_outcome_tokens_are_accumulated():
    """Input tokens on an errored result must be added to the running total."""
    results = [
        _make_errored_result("job-1", input_tokens=500, output_tokens=0),
    ]
    job_ids = {"job-1"}

    # Minimal stubs so _process_batch_results can run without a real client
    pass_ids: list[str] = []
    fail_records: list[tuple[str, str]] = []

    in_tok, out_tok, parse_failed, errored = geo_filter._process_batch_results(
        results, job_ids, pass_ids, fail_records
    )

    assert in_tok == 500, (
        "Errored-outcome input tokens must be counted — Anthropic bills them. "
        f"Got in_tok={in_tok}, expected 500."
    )
    assert errored == 1


def test_succeeded_outcome_tokens_still_counted():
    """Regression: succeeded outcomes must still accumulate tokens."""
    results = [
        _make_succeeded_result("job-2", '{"pass": true}', input_tokens=300, output_tokens=50),
    ]
    job_ids = {"job-2"}
    pass_ids: list[str] = []
    fail_records: list[tuple[str, str]] = []

    in_tok, out_tok, parse_failed, errored = geo_filter._process_batch_results(
        results, job_ids, pass_ids, fail_records
    )

    assert in_tok == 300
    assert out_tok == 50
    assert errored == 0


def test_mixed_results_accumulate_all_tokens():
    """Both errored and succeeded tokens must be summed."""
    results = [
        _make_errored_result("job-3",   input_tokens=500, output_tokens=0),
        _make_succeeded_result("job-4", '{"pass": true}', input_tokens=300, output_tokens=50),
    ]
    job_ids = {"job-3", "job-4"}
    pass_ids: list[str] = []
    fail_records: list[tuple[str, str]] = []

    in_tok, out_tok, parse_failed, errored = geo_filter._process_batch_results(
        results, job_ids, pass_ids, fail_records
    )

    assert in_tok == 800, f"Expected 500+300=800, got {in_tok}"
    assert out_tok == 50
    assert errored == 1
