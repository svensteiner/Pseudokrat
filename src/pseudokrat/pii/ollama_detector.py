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

import hashlib
import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from typing import Any

from pseudokrat.recognizers.base import Span

_DEFAULT_HOST = "http://localhost:11434"
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_MAX_CACHE_ENTRIES = 128

# Werte, die das LLM manchmal faelschlich als Eigenname zurueckgibt.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "gmbh",
        "ag",
        "kg",
        "og",
        "ug",
        "se",
        "ohg",
        "kgaa",
        "e.u",
        "eu",
        "der",
        "die",
        "das",
        "und",
        "oder",
        "firma",
        "gesellschaft",
        "konto",
        "rechnung",
        "bilanz",
        "summe",
        "betrag",
        "datum",
        "seite",
        "jahr",
        "company",
        "the",
        "and",
        "gmbh & co kg",
    }
)

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


def _validate_local_url(url: str) -> None:
    """Reject every Ollama endpoint that is not an explicit loopback URL."""
    try:
        parsed = urllib.parse.urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"Ungültige Ollama-URL: {url!r}") from exc
    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Ollama muss über eine lokale http(s)-URL angesprochen werden.")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost":
        return
    try:
        if ipaddress.ip_address(hostname).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError(
        "Externe Ollama-Hosts sind deaktiviert, damit kein Klartext den Rechner verlässt."
    )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs


def _http_urlopen(target: str | urllib.request.Request, *, timeout: float) -> Any:
    """Open a loopback-only URL without proxies or redirect following."""
    url = target.full_url if isinstance(target, urllib.request.Request) else target
    _validate_local_url(url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    return opener.open(target, timeout=timeout)  # nosec B310 - loopback validated


def ollama_available(host: str = _DEFAULT_HOST, timeout: float = 3.0) -> bool:
    """True, wenn ein Ollama-Server erreichbar ist."""
    try:
        with _http_urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return bool(resp.status == 200)
    except (urllib.error.URLError, OSError, ValueError):
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
        self._cache: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
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
        with _http_urlopen(req, timeout=self._timeout) as resp:
            raw_body = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw_body) > _MAX_RESPONSE_BYTES:
            raise ValueError("Ollama-Antwort ist unplausibel groß.")
        body = json.loads(raw_body.decode("utf-8"))
        if not isinstance(body, dict):
            return []
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

    @staticmethod
    def _is_plausible(value: str) -> bool:
        """Filtert LLM-Rauschen: keine zu kurzen/generischen/Stopwort-Werte.

        Ohne diese Schranke redigiert der Detektor sonst flächig über
        Funktionswörter oder Rechtsform-Kürzel, die das Modell faelschlich
        als Eigenname zurueckgibt.
        """
        if len(value) < 3:
            return False
        if not any(c.isupper() for c in value):  # Eigennamen sind gross
            return False
        return value.lower().strip(".") not in _STOPWORDS

    # -- Recognizer-Schnittstelle ------------------------------------------
    def analyze(self, text: str) -> list[Span]:
        stripped = text.strip()
        if len(stripped) < self._min_chars:
            return []
        normalized = " ".join(stripped.split())
        cache_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            entities = self._cache.pop(cache_key)
            self._cache[cache_key] = entities
        else:
            try:
                entities = self._query(text)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                if not self._warned:
                    self._log(f"     (Ollama-Erkenner nicht nutzbar: {exc})")
                    self._warned = True
                return []
            self._cache[cache_key] = entities
            if len(self._cache) > _MAX_CACHE_ENTRIES:
                self._cache.popitem(last=False)

        spans: list[Span] = []
        for value, category in entities:
            if not self._is_plausible(value):
                continue
            # Wortgrenzen: kein Treffer mitten in einem laengeren Wort.
            pattern = rf"(?<![A-Za-zÄÖÜäöüß0-9]){re.escape(value)}(?![A-Za-zÄÖÜäöüß0-9])"
            for match in re.finditer(pattern, text):
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
