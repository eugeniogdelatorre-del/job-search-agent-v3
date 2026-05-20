"""M5 (REVIEW.md, 2026-05-20): notify.py ALERT_RECIPIENT is hardcoded to
Eugenio's email. Federico/Ana never receive failure notifications.

Fix: read from NOTIFY_RECIPIENTS env var (comma-separated list of emails).
Fall back to the hardcoded address when the env var is absent so existing
deployments without the secret are unaffected.
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import scraper.notify as notify


def _reload_with_env(**env_overrides):
    """Reload notify module with a custom env and return the module."""
    with patch.dict(os.environ, env_overrides, clear=False):
        return importlib.reload(notify)


def test_default_recipient_when_env_not_set():
    """Without NOTIFY_RECIPIENTS set, the hardcoded address is used."""
    env = {k: v for k, v in os.environ.items() if k != "NOTIFY_RECIPIENTS"}
    with patch.dict(os.environ, env, clear=True):
        mod = importlib.reload(notify)
    assert "eugeniogdelatorre@gmail.com" in mod.ALERT_RECIPIENTS


def test_single_recipient_from_env():
    """A single address in NOTIFY_RECIPIENTS replaces the default."""
    with patch.dict(os.environ, {"NOTIFY_RECIPIENTS": "alice@example.com"}):
        mod = importlib.reload(notify)
    assert mod.ALERT_RECIPIENTS == ["alice@example.com"]


def test_multiple_recipients_from_env():
    """Comma-separated addresses are split into a list."""
    with patch.dict(os.environ, {"NOTIFY_RECIPIENTS": "a@x.com, b@x.com, c@x.com"}):
        mod = importlib.reload(notify)
    assert mod.ALERT_RECIPIENTS == ["a@x.com", "b@x.com", "c@x.com"]


def test_payload_uses_recipients_list():
    """_build_payload sends to the full ALERT_RECIPIENTS list."""
    recipients = ["x@x.com", "y@y.com"]
    import json
    payload = json.loads(notify._build_payload("test-wf", "http://run", "", recipients).decode())
    assert payload["to"] == recipients
