"""Shared helpers for the Batch API + JSON parsing pipeline.

`classify.py` and `cv_score.py` both:
    1. Construct an Anthropic SDK client from ``ANTHROPIC_API_KEY``.
    2. Submit a Batch, then poll ``messages.batches.retrieve`` until
       ``processing_status == 'ended'`` (or a timeout).
    3. Parse the model's text response as JSON, tolerating the occasional
       ```json fence the model adds despite the prompt.

Pulling these into one module removes character-identical duplicates and
gives us one place to evolve the polling/timeouts. Module name is
underscore-prefixed because it's an internal helper, not a public surface.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

# 30-second poll interval × 50 attempts = 25 minutes max wait, matching
# the prior individual constants in classify.py / cv_score.py.
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_POLL_MAX_SECONDS = 25 * 60


def get_anthropic_client():
    """Build an Anthropic client or print a clear failure and return None.

    Centralizes the three failure modes (missing key, missing SDK, init
    error) so callers always see the same error format and don't need to
    duplicate the import-guard. Returns ``None`` on any failure — callers
    treat ``None`` as "abort this run, no AI work possible."
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("  [fatal] ANTHROPIC_API_KEY missing", file=sys.stderr)
        return None
    try:
        from anthropic import Anthropic  # type: ignore
    except ImportError:
        print("  [fatal] anthropic SDK not installed", file=sys.stderr)
        return None
    try:
        return Anthropic(api_key=key)
    except Exception as e:
        print(f"  [fatal] Anthropic client init failed: {e}", file=sys.stderr)
        return None


def poll_batch(
    anthropic_client,
    batch_id: str,
    *,
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_seconds: int = DEFAULT_POLL_MAX_SECONDS,
):
    """Block until the batch reaches ``processing_status == 'ended'`` or we time out.

    Transient retrieve errors (network blips, 5xx) are logged and retried;
    they don't abort. We rely on the deadline to bound the loop. If we time
    out the next cron run picks up the work — this is by design, see
    ``DEFAULT_POLL_MAX_SECONDS`` versus the 30-min Actions job timeout.
    """
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        try:
            batch = anthropic_client.messages.batches.retrieve(batch_id)
        except Exception as e:
            print(f"  [anthropic] poll failed (will retry): {e}", file=sys.stderr)
            time.sleep(interval_seconds)
            continue
        status = getattr(batch, "processing_status", None)
        counts = getattr(batch, "request_counts", None)
        print(f"  [poll] status={status}  counts={counts}")
        if status == "ended":
            return batch
        time.sleep(interval_seconds)
    print("  [poll] timed out — next cron run will pick up the pieces", file=sys.stderr)
    return None


# Some Haiku 4.5 responses wrap JSON in ```json ... ``` fences despite the
# system prompt forbidding it. Strip both opening (```json or just ```)
# and closing fences before json.loads.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def extract_json(text: str) -> dict | None:
    """Parse JSON from the model's text block, tolerating fences and prose.

    Strategy:
        1. Strip code fences and whitespace.
        2. Try a clean json.loads on the result.
        3. As a last resort, regex out the first ``{...}`` block (handles
           the case where the model adds an apology before/after the JSON).

    Returns ``None`` if every attempt fails — the caller decides whether to
    retry, log, or skip the row.
    """
    stripped = _FENCE_RE.sub("", text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
