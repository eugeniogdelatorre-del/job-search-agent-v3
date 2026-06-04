"""Bug (2026-06-04 review #7): estimate_rescore_cost._count_cv_score_scope
hard-codes ``score_total >= 60``, but cv_score's real eligibility floor is
``WARM_THRESHOLD = 40`` (lowered 60→40 on 2026-05-13). The estimator therefore
omits the 40-59 band and under-counts the rescore cost.

Fix: filter on cv_score.WARM_THRESHOLD instead of the literal 60.
"""
from __future__ import annotations

from scraper import estimate_rescore_cost
from scraper.cv_score import WARM_THRESHOLD


class _FakeQuery:
    """Records the score_total threshold passed to .gte()."""

    def __init__(self, sink):
        self._sink = sink

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, col, val):
        if col == "score_total":
            self._sink["score_total"] = val
        return self

    def execute(self):
        return type("R", (), {"count": 0})()


class _FakeClient:
    def __init__(self, sink):
        self._sink = sink

    def table(self, *_a, **_k):
        return _FakeQuery(self._sink)


def test_cv_score_scope_uses_warm_threshold():
    sink: dict = {}
    estimate_rescore_cost._count_cv_score_scope(_FakeClient(sink), "2026-01-01T00:00:00+00:00")
    assert sink.get("score_total") == WARM_THRESHOLD
    assert WARM_THRESHOLD == 40  # guards against silent drift back to 60
