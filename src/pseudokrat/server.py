"""Lokaler HTTP-Server für das Excel-Add-in (Phase 5).

Bindet ausschließlich an ``127.0.0.1`` und akzeptiert nur Requests mit
einem gültigen Bearer-Token. Der Token wird beim Start einmal generiert
und in eine Datei unter ``%LOCALAPPDATA%/Pseudokrat/server_token.txt``
geschrieben — von dort liest das Add-in ihn beim ersten Aufruf.

CORS: Wir spiegeln die Origin nur, wenn sie auf ``127.0.0.1``,
``localhost``, ``excel.officeapps.live.com`` oder ``outlook.office.com``
zeigt. Andere Origins werden hart abgelehnt — ein bösartiges Tab kann
sich nicht hineinklinken.

**Status: Scaffold.** Reicht aus, damit das Excel-Add-in-Taskpane gegen
ein lokales Pseudokrat sprechen kann. Produktion verlangt zusätzlich
HTTPS-Zertifikat (siehe ``office-addin-dev-certs``).
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from pseudokrat import __version__
from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.pii.privacy_filter import load_default_detector
from pseudokrat.recognizers import recognizers_for_store
from pseudokrat.store.profile import ProfileManager
from pseudokrat.store.secure_db import InvalidPasswordError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 31337
ALLOWED_ORIGINS = (
    "https://127.0.0.1",
    "https://localhost",
    "https://excel.officeapps.live.com",
    "https://outlook.office.com",
)

#: Defense-in-depth-Headers für alle JSON-Responses. Wir liefern aktuell
#: keinen HTML-Content aus — die Header sind trotzdem nützlich, falls ein
#: Pentest oder eine Browser-Anomalie versucht, die Response als HTML zu
#: interpretieren (MIME-Sniffing) oder in einem Frame einzubetten.
#: Cache-Control verhindert, dass Mandanten-Texte versehentlich in einem
#: Proxy- oder Browser-Cache liegen bleiben.
_SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    (
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    ),
    ("Cache-Control", "no-store, no-cache, must-revalidate, private"),
    ("Pragma", "no-cache"),
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains"),
    ("Permissions-Policy", "interest-cohort=()"),
)


class TokenStore:
    """Hält + persistiert das Server-Bearer-Token."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._token: str | None = None

    def ensure(self) -> str:
        if self._token is not None:
            return self._token
        if self.path.exists():
            try:
                token = self.path.read_text(encoding="ascii").strip()
                if token:
                    self._token = token
                    return token
            except OSError:
                pass
        token = secrets.token_urlsafe(32)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(token, encoding="ascii")
        self._token = token
        return token


@dataclass
class ServerState:
    profile_manager: ProfileManager
    profile_name: str
    password: str
    token_store: TokenStore
    no_ml: bool = False
    _store: object | None = field(default=None, init=False, repr=False)

    def open_session(
        self,
    ) -> tuple[Anonymizer, Deanonymizer]:
        from pseudokrat.store.mapping_store import MappingStore

        store, audit = self.profile_manager.open_or_create(
            self.profile_name, self.password
        )
        assert isinstance(store, MappingStore)
        self._store = store
        settings = self.profile_manager.settings
        detector = None if self.no_ml else load_default_detector(settings)
        anonymizer = Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=detector,
            audit_log=audit,
            model_version=settings.model_id if not settings.disable_ml else "disabled",
        )
        deanonymizer = Deanonymizer(
            store=store,
            audit_log=audit,
            model_version=settings.model_id if not settings.disable_ml else "disabled",
        )
        return anonymizer, deanonymizer

    def close(self) -> None:
        if self._store is not None:
            self._store.close()  # type: ignore[attr-defined]
            self._store = None


def _origin_allowed(origin: str | None) -> str | None:
    if origin is None:
        return None
    for prefix in ALLOWED_ORIGINS:
        if origin.startswith(prefix):
            return origin
    return None


class _RequestHandler(BaseHTTPRequestHandler):
    state: ServerState  # injected by make_handler

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Logging über structlog, nicht stderr-Direct-Print."""
        from pseudokrat.logging_config import get_logger

        get_logger("pseudokrat.server").info(
            "http", method=self.command, path=self.path, args=args
        )

    # ----- helpers ----------------------------------------------------------

    def _require_token(self) -> bool:
        provided = self.headers.get("Authorization", "")
        expected = self.state.token_store.ensure()
        if not provided.startswith("Bearer "):
            self._send_json(401, {"error": "missing-bearer"})
            return False
        if not secrets.compare_digest(provided[len("Bearer ") :], expected):
            self._send_json(401, {"error": "invalid-bearer"})
            return False
        return True

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        self.send_header("Vary", "Origin")
        allowed = _origin_allowed(self.headers.get("Origin"))
        if allowed is not None:
            self.send_header("Access-Control-Allow-Origin", allowed)
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ----- routes -----------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP-Server-API
        self._send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802 - HTTP-Server-API
        if self.path == "/health":
            profiles = [p.name for p in self.state.profile_manager.list_profiles()]
            self._send_json(200, {"version": __version__, "profiles": profiles})
            return
        self._send_json(404, {"error": "not-found"})

    def do_POST(self) -> None:  # noqa: N802 - HTTP-Server-API
        if not self._require_token():
            return
        if self.path in ("/v1/anonymize", "/v1/deanonymize"):
            body = self._read_body()
            texts_raw = body.get("texts", [])
            if not isinstance(texts_raw, list):
                self._send_json(400, {"error": "texts-must-be-list"})
                return
            texts: list[str] = [str(t) for t in texts_raw]
            try:
                anonymizer, deanonymizer = self.state.open_session()
                try:
                    if self.path.endswith("/anonymize"):
                        results = [
                            {"input": t, "output": anonymizer.anonymize(t).text}
                            for t in texts
                        ]
                    else:
                        results = [
                            {"input": t, "output": deanonymizer.deanonymize(t).text}
                            for t in texts
                        ]
                finally:
                    self.state.close()
            except InvalidPasswordError as exc:
                self._send_json(401, {"error": str(exc)})
                return
            self._send_json(200, {"results": results})
            return
        self._send_json(404, {"error": "not-found"})


def make_handler(state: ServerState) -> type[_RequestHandler]:
    """Bindet den ServerState an eine HTTPHandler-Subklasse."""

    class Bound(_RequestHandler):
        pass

    Bound.state = state
    return Bound


@dataclass
class RunningServer:
    httpd: HTTPServer
    thread: threading.Thread
    state: ServerState

    def stop(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=5)


def start_server(
    state: ServerState,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    in_background: bool = True,
) -> RunningServer:
    """Startet den HTTP-Server. ``in_background=False`` blockt im aktuellen Thread."""
    handler_cls = make_handler(state)
    httpd = HTTPServer((host, port), handler_cls)
    if in_background:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="pseudokrat-server")
        thread.start()
    else:
        thread = threading.current_thread()
    return RunningServer(httpd=httpd, thread=thread, state=state)


__all__ = (
    "ALLOWED_ORIGINS",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "RunningServer",
    "ServerState",
    "TokenStore",
    "start_server",
)


def security_headers() -> tuple[tuple[str, str], ...]:
    """Liefert die statischen Defense-in-Depth-Header. Für Tests + Audit-Doku."""
    return _SECURITY_HEADERS
