"""Bug (2026-06-04 review #9): the workable parser matches individual
job-apply URLs of the form ``apply.workable.com/j/<shortcode>/`` as if ``j``
were an account slug. ``/j/`` is Workable's reserved per-job path (the parser
itself builds such URLs), never an account board.

Fix: exclude the reserved ``/j/`` path from can_parse.
"""
from __future__ import annotations

from scraper.parsers.workable import can_parse


def test_individual_job_apply_url_not_matched():
    assert can_parse({"url": "https://apply.workable.com/j/ABC123/"}) is False


def test_account_board_still_matched():
    """Regression: a real account board must still parse."""
    assert can_parse({"url": "https://apply.workable.com/nalamoney/"}) is True


def test_account_starting_with_j_still_matched():
    """A slug that merely starts with 'j' is not the reserved /j/ path."""
    assert can_parse({"url": "https://apply.workable.com/jito-labs"}) is True
