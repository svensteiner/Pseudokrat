"""Recognizer für offensichtliche API-Schlüssel und Tokens.

Konservativ: nur Patterns mit eindeutigem Präfix oder Struktur, damit normale
Identifier (Hashes, UUIDs, Build-Nummern) nicht versehentlich maskiert werden.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    # OpenAI API keys (sk-, sk-proj-, sk-svcacct-)
    (
        "openai",
        re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_\-]{20,}"),
        0.95,
    ),
    # Anthropic API keys
    (
        "anthropic",
        re.compile(r"(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_\-]{20,}"),
        0.95,
    ),
    # AWS Access Keys
    (
        "aws_access",
        re.compile(
            r"(?<![A-Za-z0-9])(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}(?![A-Za-z0-9])"
        ),
        0.95,
    ),
    # GitHub tokens (ghp, gho, ghu, ghs, ghr, github_pat_)
    (
        "github",
        re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,251}(?![A-Za-z0-9])"),
        0.95,
    ),
    (
        "github_pat",
        re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
        0.95,
    ),
    # Slack tokens
    (
        "slack",
        re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9\-]{10,}"),
        0.9,
    ),
    # Google API keys
    (
        "google",
        re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{35}(?![A-Za-z0-9])"),
        0.9,
    ),
    # JWT (three base64url-segments)
    (
        "jwt",
        re.compile(
            r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"
        ),
        0.9,
    ),
    # Generic Bearer token in Authorization headers
    (
        "bearer",
        re.compile(r"(?<=Bearer\s)[A-Za-z0-9_\-\.=]{20,}"),
        0.8,
    ),
)


class SecretRecognizer:
    """API-Schlüssel, Tokens, Bearer-Strings."""

    name = "secret"
    category = "SECRET"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen_ranges: list[tuple[int, int]] = []
        for _label, pattern, score in _PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if any(start < e and end > s for s, e in seen_ranges):
                    continue
                seen_ranges.append((start, end))
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        category=self.category,
                        text=match.group(0),
                        score=score,
                    )
                )
        return spans
