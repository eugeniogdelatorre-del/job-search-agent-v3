"""Shared prompt-injection defence used by classify.py and cv_score.py.

C2-new (REVIEW.md, 2026-05-20): the H6 strip was applied to cv_score
but not classify; classify runs first so mis-classifications propagate.
Centralising the regex here ensures both files stay in sync.

Usage:
    from scraper._prompt_safety import strip_injection

    desc = strip_injection(raw_description)
"""
from __future__ import annotations

import re

# Phrases that signal an attempt to hijack the model's instructions.
# The regex is intentionally conservative — false positives (real job
# descriptions that happen to contain these phrases) are unlikely and
# the downside is a "[redacted]" token in a field Haiku doesn't weight
# heavily.  Extend the alternation here if new vectors are found; both
# callers benefit from a single edit.
_INJECTION_RE = re.compile(
    # "ignore/disregard/forget [all|the|your|any] previous|prior|above|earlier
    #  instructions|prompt(s)" — tolerant of an optional qualifier and several
    #  target words, since "ignore all previous instructions" and "ignore the
    #  above instructions" are the common real-world variants.
    r"(?:(?:ignore|disregard|forget)\s+(?:all\s+|the\s+|your\s+|any\s+|these\s+)?"
    r"(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompts?)"
    r"|disregard\s+all"
    r"|system\s*[:\xb7]"        # "System:" or "System·"
    r"|</?system>"               # XML-style <system> / </system>
    r"|###\s*instructions?"      # markdown heading attack
    r"|<\|im_start\|>\s*system"  # chat-template injection
    r")",
    re.IGNORECASE,
)


def strip_injection(text: str) -> str:
    """Replace known injection phrases with '[redacted]'.

    Safe to call on any string; returns the input unchanged when no
    injection patterns are found.
    """
    return _INJECTION_RE.sub("[redacted]", text)
