"""Housekeeping guard (2026-05-20): every *required* env var consumed by
scraper/ must be wired into at least one .github/workflows/*.yml file.

Motivation: C1-new from the 2026-05-20 re-review was exactly this class
of bug — PIPELINE_OWNER_USER_ID was added to the Python scripts but
never added to the YAML env blocks, causing silent exit-2 failures.

How this works:
  - REQUIRED_VARS is the explicit list of secrets that must appear in
    workflows. Optional vars (those with a safe fallback default such as
    GEO_FALLBACK_LOCATION, RESEND_FROM, CANDIDATE_LOCATION, etc.) are
    intentionally excluded — their absence is expected and safe.
  - For each required var, we assert that the string appears in at least
    one of the four paid-AI workflow files.
  - Add new required vars here whenever a new `os.environ.get("X")` is
    promoted from "optional with fallback" to "required for correctness".
"""
from __future__ import annotations

import pathlib

import pytest

# Workflow files that run paid AI stages and must have all required vars.
WORKFLOW_FILES = [
    pathlib.Path(".github/workflows/cv_score.yml"),
    pathlib.Path(".github/workflows/geo_filter.yml"),
    pathlib.Path(".github/workflows/weekly_summary.yml"),
    pathlib.Path(".github/workflows/pipeline.yml"),
]

# Required env vars: those whose absence causes incorrect behaviour
# (not just a degraded-but-safe fallback).
REQUIRED_VARS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "ANTHROPIC_API_KEY",
    "RESEND_API_KEY",
    "PIPELINE_OWNER_USER_ID",
]


@pytest.fixture(scope="module")
def workflow_texts() -> dict[str, str]:
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    return {
        str(wf): (root / wf).read_text(encoding="utf-8")
        for wf in WORKFLOW_FILES
    }


@pytest.mark.parametrize("var", REQUIRED_VARS)
def test_required_env_var_in_workflows(var: str, workflow_texts: dict[str, str]) -> None:
    """Each required env var must appear in at least one workflow file."""
    present = [path for path, text in workflow_texts.items() if var in text]
    assert present, (
        f"Required env var '{var}' is not referenced in any workflow file.\n"
        f"Checked: {list(workflow_texts)}\n"
        "Add it to the relevant env: blocks in .github/workflows/. "
        "See C1-new (2026-05-20) for the failure mode this prevents."
    )
