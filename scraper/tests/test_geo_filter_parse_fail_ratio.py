"""Bug (2026-06-04 review #2): geo_filter computed its parse-fail safety ratio
against an inflated denominator. Errored and parse-failed jobs are appended to
``pass_ids`` (fail-open) *and* counted in ``parse_failed``/``errored``, so
``total_results = len(pass_ids) + len(fail_records) + parse_failed + errored``
double-counts them. The true failure rate is understated and the hard-fail
circuit breaker (20%) won't trip when it should.

Fix: count one result per batch outcome. New helpers ``_collect_batch_outcomes``
(counts ``total_results`` correctly) and ``_parse_fail_status`` (ratio → status).
"""
from __future__ import annotations

from types import SimpleNamespace

from scraper import geo_filter


def _succeeded(custom_id: str, text: str):
    usage = SimpleNamespace(input_tokens=10, output_tokens=5)
    block = SimpleNamespace(type="text", text=text)
    message = SimpleNamespace(usage=usage, content=[block])
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type="succeeded", message=message))


def test_parse_fail_status_uses_true_denominator():
    # 21 parse-fails out of 100 results = 21% > 20% hard-fail threshold.
    assert geo_filter._parse_fail_status(21, 100) == "hard_fail"
    assert geo_filter._parse_fail_status(10, 100) == "warn"
    assert geo_filter._parse_fail_status(2, 100) == "ok"
    assert geo_filter._parse_fail_status(0, 0) == "ok"


def test_collect_counts_each_result_once():
    # 79 clean passes + 21 parse-failures (unparseable JSON) = 100 results.
    results = []
    job_ids = set()
    for i in range(79):
        cid = f"ok-{i}"
        job_ids.add(cid)
        results.append(_succeeded(cid, '{"eligible": true}'))
    for i in range(21):
        cid = f"bad-{i}"
        job_ids.add(cid)
        results.append(_succeeded(cid, "this is not json"))

    summary = geo_filter._collect_batch_outcomes(results, job_ids)

    # total_results must equal the number of results, NOT the inflated sum
    # (which would be 100 passes + 21 parse_failed = 121).
    assert summary.total_results == 100
    assert summary.parse_failed == 21
    assert len(summary.pass_ids) == 100  # 79 clean + 21 fail-open
    assert geo_filter._parse_fail_status(summary.parse_failed, summary.total_results) == "hard_fail"
