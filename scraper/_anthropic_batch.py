"""Shared helpers for the Batch API + JSON parsing pipeline.

`classify.py`, `geo_filter.py`, and `cv_score.py` all:
    1. Construct an Anthropic SDK client from ``ANTHROPIC_API_KEY``.
    2. Submit a Batch, then poll ``messages.batches.retrieve`` until
       ``processing_status == 'ended'`` (or a timeout).
    3. Parse the model's text response as JSON, tolerating the occasional
       ```json fence the model adds despite the prompt.

Pulling these into one module removes character-identical duplicates and
gives us one place to evolve the polling / timeouts. Module name is
underscore-prefixed because it's an internal helper, not a public surface.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

# Anthropic Batch API does not advertise an SLA — most batches return in
# a few minutes, but a 5-job batch was observed sitting in `processing`
# for >25 minutes on 2026-05-07 (run #25493119564). The 25-minute cap was
# too aggressive: it killed the poll mid-batch, which orphans the batch
# (Anthropic still bills for it once it completes) and skips the
# write-back. Bumped to 50 minutes; the surrounding workflow's
# `timeout-minutes` is bumped to 55 so we still leave 5 minutes of slack
# for write-back + spend logging.
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_POLL_MAX_SECONDS = 50 * 60


def get_anthropic_client():
    """Build an Anthropic client or print a clear failure and return None.

    Centralizes the three failure modes (missing key, missing SDK, init
    error) so callers always see the same error format. Returns ``None``
    on any failure — callers treat ``None`` as "abort this run, no AI
    work possible."
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


# Per the Batch API docs, ``processing_status`` is one of ``in_progress``,
# ``canceling``, or ``ended``. ``canceling`` is transient — it always
# resolves to ``ended`` — so we keep polling through it. Anything outside
# this set is treated as terminal: we return the batch and let the caller
# inspect ``request_counts`` to decide what to write back. That's the
# defensive choice if Anthropic ever introduces a new terminal status
# (e.g. a hypothetical ``failed``/``expired``) — better to exit the poll
# loop and salvage partial results than to hang the full 50-min deadline.
_BATCH_IN_PROGRESS_STATUSES = frozenset({"in_progress", "canceling"})

# Bail out after this many consecutive retrieve() failures rather than
# silently riding the deadline through a sustained Anthropic outage.
# 6 × 30s ≈ 3 minutes of failed polling before we give up — generous
# enough for transient blips, short enough to surface a real outage to
# the next cron.
_MAX_CONSECUTIVE_POLL_ERRORS = 6


def poll_batch(
    anthropic_client,
    batch_id: str,
    *,
    interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    max_seconds: int = DEFAULT_POLL_MAX_SECONDS,
):
    """Block until processing_status leaves the in-progress set or we time out.

    Returns the final batch object on any terminal status, or ``None`` on
    timeout / sustained retrieve failure. Caller is expected to inspect
    ``processing_status`` and ``request_counts`` before iterating
    ``messages.batches.results(...)``.

    Transient retrieve errors (network blips, 5xx) are logged and retried;
    after ``_MAX_CONSECUTIVE_POLL_ERRORS`` in a row we bail so the next cron
    run picks up the work instead of burning the full deadline.
    """
    deadline = time.time() + max_seconds
    consecutive_errors = 0
    while time.time() < deadline:
        try:
            batch = anthropic_client.messages.batches.retrieve(batch_id)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(
                f"  [anthropic] poll failed "
                f"({consecutive_errors}/{_MAX_CONSECUTIVE_POLL_ERRORS}, "
                f"will retry): {e}",
                file=sys.stderr,
            )
            if consecutive_errors >= _MAX_CONSECUTIVE_POLL_ERRORS:
                print(
                    "  [anthropic] giving up after consecutive poll errors — "
                    "next cron run will pick up the pieces",
                    file=sys.stderr,
                )
                return None
            time.sleep(interval_seconds)
            continue
        if batch is None:
            # Defensive — the SDK shouldn't return None, but if it does we
            # don't want to silently treat status=None as in-progress and
            # loop the full deadline.
            print(
                "  [anthropic] retrieve returned None; aborting poll",
                file=sys.stderr,
            )
            return None
        status = getattr(batch, "processing_status", None)
        counts = getattr(batch, "request_counts", None)
        print(f"  [poll] status={status}  counts={counts}")
        if status not in _BATCH_IN_PROGRESS_STATUSES:
            if status != "ended":
                # Future-terminal status (or a None status from a
                # malformed response). Return so the caller can decide
                # based on request_counts; log loudly so it shows up in
                # the workflow run.
                print(
                    f"  [poll] terminal status={status!r} (expected 'ended') — "
                    "caller should inspect request_counts before write-back",
                    file=sys.stderr,
                )
            return batch
        time.sleep(interval_seconds)
    print("  [poll] timed out — next cron run will pick up the pieces", file=sys.stderr)
    return None


# Some Haiku 4.5 responses wrap JSON in ```json ... ``` fences despite the
# system prompt forbidding it. Strip both opening (```json or just ```)
# and closing fences before json.loads.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _first_balanced_json_object(s: str) -> str | None:
    """Return the first complete top-level JSON object in ``s``.

    Audit M3: the previous fallback used ``re.search(r"\\{.*\\}", ...)`` with
    a greedy ``.*``, so a response that legitimately contained the model's
    JSON followed by trailing prose with stray braces would span first ``{``
    to LAST ``}`` and fail to parse. Walking brace depth byte-by-byte is
    cheap and gives us the actual first balanced object.

    Naively tracks strings so a ``}`` inside a string doesn't close the
    object early. Escapes inside strings are honored.
    """
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue  # stray closer before any opener — ignore
            depth -= 1
            if depth == 0 and start >= 0:
                return s[start : i + 1]
    return None


def extract_json(text: str) -> dict | None:
    """Parse JSON from the model's text block, tolerating fences and prose.

    1. Strip code fences and whitespace.
    2. Try a clean json.loads on the result.
    3. As a last resort, walk brace depth to extract the first balanced
       ``{...}`` block (handles responses where the model adds an
       apology before/after the JSON, or trailing prose with stray
       braces — audit M3).

    Returns ``None`` if every attempt fails — the caller decides whether
    to retry, log, or skip the row.
    """
    stripped = _FENCE_RE.sub("", text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass
    block = _first_balanced_json_object(stripped)
    if not block:
        return None
    try:
        return json.loads(block)
    except Exception:
        return None
