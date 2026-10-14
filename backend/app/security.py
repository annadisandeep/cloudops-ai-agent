"""Security utilities: secret redaction and in-memory rate limiting.

The rate limiter is a per-process sliding window keyed by client IP — adequate
for a single-instance MVP and documented as such (use a gateway/redis-backed
limiter for multi-instance deployments).
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

# --- Secret redaction ---------------------------------------------------------

_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # AWS access key IDs
    (re.compile(r"\b(AKIA|ASIA|AIDA|AROA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_KEY_ID]"),
    # Likely AWS secret keys when labeled
    (
        re.compile(
            r"(?i)(aws_?secret(?:_access)?_?key\s*[=:]\s*)[A-Za-z0-9/+=]{20,}"
        ),
        r"\1[REDACTED]",
    ),
    # Google API keys
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    # Bearer / OAuth tokens
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1[REDACTED]"),
    # Generic labeled secrets: password=..., token=..., api_key=..., secret=...
    (
        re.compile(r"(?i)\b((?:password|passwd|pwd|token|api[_-]?key|secret|client[_-]?secret)\s*[=:]\s*)\S+"),
        r"\1[REDACTED]",
    ),
    # Private key blocks
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    # GitHub tokens
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "[REDACTED_GITHUB_TOKEN]"),
]


def redact_secrets(text: str) -> str:
    """Redact obvious credential material from untrusted text (e.g. log lines)
    before it is stored, displayed, or passed to an LLM."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# --- Rate limiting ------------------------------------------------------------


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window limiter keyed by caller id."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        cutoff = now - self.window
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                return False
            hits.append(now)
            return True
