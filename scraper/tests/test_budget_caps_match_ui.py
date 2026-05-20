"""C1 (REVIEW.md, 2026-05-19): the monthly cap and per-stage caps must
agree between the Python pipeline (scraper/budget.py) and the web UI
(web/src/lib/budget-config.ts).

Before this test landed, the three places the cap was declared had drifted
to $30 / $20 / $8 (backend / UI / README), and the per-stage caps disagreed
on geo_filter (5 vs 3) and cv_score (20 vs 12). Operator looking at
/settings saw the wrong headroom; README claim was off by ~4x.

Drift in either direction now fails CI. The canonical numbers live in
scraper/budget.py (per the comment in budget-config.ts). Touch both files
in the same commit.
"""
from __future__ import annotations

import pathlib
import re

from scraper import budget


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BUDGET_TS = REPO_ROOT / "web" / "src" / "lib" / "budget-config.ts"


def test_ui_monthly_cap_matches_budget_py():
    ts = BUDGET_TS.read_text(encoding="utf-8")
    m = re.search(r"MONTHLY_CAP_USD\s*=\s*(\d+)", ts)
    assert m, "MONTHLY_CAP_USD declaration not found in budget-config.ts"
    assert int(m.group(1)) == int(budget.BUDGET_CAP_USD), (
        f"web/src/lib/budget-config.ts MONTHLY_CAP_USD={m.group(1)} drifted "
        f"from scraper/budget.py BUDGET_CAP_USD={budget.BUDGET_CAP_USD}"
    )


def test_ui_stage_caps_match_budget_py():
    ts = BUDGET_TS.read_text(encoding="utf-8")
    for stage, cap in budget.STAGE_BUDGETS.items():
        m = re.search(rf"{stage}\s*:\s*(\d+)", ts)
        assert m, f"stage {stage!r} cap not found in budget-config.ts"
        assert int(m.group(1)) == int(cap), (
            f"web/src/lib/budget-config.ts STAGE_CAPS_USD.{stage}={m.group(1)} "
            f"drifted from scraper/budget.py STAGE_BUDGETS[{stage!r}]={cap}"
        )
