"""URL-Recognizer für http(s)- und www-Adressen.

Reine Regex, kein DNS-Lookup. Erkennt Standard-URLs mit Schema (`https://`,
`http://`, `ftp://`) sowie schema-lose `www.…`-Adressen. Trailing-Punctuation
(`.`, `,`, `;`, `)`) wird vom Match abgeschnitten — sonst würden Satzzeichen
am Ende von URLs verloren ausschauen wie Teil der URL.
"""

from __future__ import annotations

import re

from pseudokrat.recognizers.base import Span

_SCHEME_RE = re.compile(
    r"\b(?:https?|ftp)://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE,
)

_WWW_RE = re.compile(
    r"(?<!\w)www\.[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE,
)

_TRAILING_PUNCT = ".,;:!?)]}\"'"


def _trim_trailing_punct(text: str) -> str:
    while text and text[-1] in _TRAILING_PUNCT:
        text = text[:-1]
    return text


class UrlRecognizer:
    """URLs (http, https, ftp, www.)."""

    name = "url"
    category = "URL"

    def analyze(self, text: str) -> list[Span]:
        spans: list[Span] = []
        seen_ranges: list[tuple[int, int]] = []

        for pattern, score in ((_SCHEME_RE, 0.95), (_WWW_RE, 0.85)):
            for match in pattern.finditer(text):
                start = match.start()
                raw = match.group(0)
                trimmed = _trim_trailing_punct(raw)
                if not trimmed:
                    continue
                end = start + len(trimmed)
                # Mindestens ein Punkt im Host, damit "https://x" nicht matched.
                if "." not in trimmed:
                    continue
                if any(start < e and end > s for s, e in seen_ranges):
                    continue
                seen_ranges.append((start, end))
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        category=self.category,
                        text=trimmed,
                        score=score,
                    )
                )
        return spans
