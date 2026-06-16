"""Lokaler LLM-Erkenner via Ollama (z. B. Mistral).

Erkennt **generisch** identifizierende Eigennamen (Firmen-/Organisations-/
Markennamen, Personennamen, vollstaendige Adressen), die die regelbasierten
Recognizer nicht von allein finden — z. B. ein Markenname wie „Hankook" ohne
Rechtsform-Suffix. Laeuft komplett **lokal** gegen einen Ollama-Server
(Standard: ``http://localhost:11434``); es verlaesst nichts den Rechner.

Bewusst als zusaetzlicher Recognizer (``analyze(text) -> list[Span]``)
implementiert, damit er sich nahtlos in das bestehende Bundle einfuegt. Treffer
bekommen einen moderaten Score (0.6), sodass strukturierte Recognizer (IBAN,
Firma mit Suffix …) bei Ueberlappung gewinnen.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from pseudokrat.recognizers.base import Span

_DEFAULT_HOST = "http://localhost:11434"

# LLM-Entitaetstyp -> Pseudokrat-Kategorie (steuert den Platzhalter).
_TYPE_MAP = {
    "ORG": "COMPANY",
    "ORGANISATION": "COMPANY",
    "ORGANIZATION": "COMPANY",
    "COMPANY": "COMPANY",
    "FIRMA": "COMPANY",
    "BRAND": "COMPANY",
    "MARKE": "COMPANY",
    "PERSON": "PERSON",
    "NAME": "PERSON",
    "ADDRESS": "ADDRESS",
    "ADRESSE": "ADDRESS",
    "LOCATION": "ADDRESS",
    "ORT": "ADDRESS",
}

_PROMPT = (
    "Du bist ein Anonymisierungs-Assistent fuer Wirtschaftspruefer. Finde im "
    "folgenden Text ALLE identifizierenden Eigennamen: Firmen-, Organisations- "
    "und Markennamen, Personennamen sowie vollstaendige Adressen. Gib NUR exakte "
    "Textausschnitte zurueck (genau wie im Text geschrieben). Keine generischen "
    "Begriffe, keine Zahlen, keine Funktionsbezeichnungen. Antworte als JSON-"
    'Objekt der Form {"entities":[{"text":"...","type":"ORG|PERSON|ADDRESS"}]}.\n\n'
    "Text:\n"
)


def ollama_available(host: str = _DEFAULT_HOST, timeout: float = 3.0) -> bool:
    """True, wenn ein Ollama-Server erreichbar ist."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


class OllamaDetector:
    """Generischer Eigennamen-Erkenner via lokalem Ollama-LLM."""

    name = "ollama"

    def __init__(
        self,
        model: str = "mistral:latest",
        host: str = _DEFAULT_HOST,
        *,
        min_chars: int = 20,
        timeout: float = 120.0,
        log: Any = None,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._min_chars = min_chars
        self._timeout = timeout
        self._log = log or (lambda _m: None)
        self._cache: dict[str, list[tuple[str, str]]] = {}
        self._warned = False

    # -- LLM-Aufruf ---------------------------------------------------------
    def _query(self, text: str) -> list[tuple[str, str]]:
        payload = json.dumps(
            {
                "model": self._model,
                "prompt": _PROMPT + text,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        raw = body.get("response", "")
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        entities = parsed.get("entities", []) if isinstance(parsed, dict) else []
        out: list[tuple[str, str]] = []
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            value = str(ent.get("text", "")).strip()
            etype = str(ent.get("type", "")).strip().upper()
            category = _TYPE_MAP.get(etype, "COMPANY")
            if len(value) >= 2:
                out.append((value, category))
        return out

    # -- Recognizer-Schnittstelle ------------------------------------------
    def analyze(self, text: str) -> list[Span]:
        stripped = text.strip()
        if len(stripped) < self._min_chars:
            return []
        if text in self._cache:
            entities = self._cache[text]
        else:
            try:
                entities = self._query(text)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                if not self._warned:
                    self._log(f"     (Ollama-Erkenner nicht nutzbar: {exc})")
                    self._warned = True
                return []
            self._cache[text] = entities

        spans: list[Span] = []
        for value, category in entities:
            for match in re.finditer(re.escape(value), text):
                spans.append(
                    Span(
                        start=match.start(),
                        end=match.end(),
                        category=category,
                        text=value,
                        score=0.6,
                    )
                )
        return spans
