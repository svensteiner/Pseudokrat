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

import contextlib
import json
import os
import re
import secrets
import stat
import tempfile
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pseudokrat import __version__
from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.pii.privacy_filter import load_default_detector
from pseudokrat.rate_limit import TokenBucket, bucket_from_env
from pseudokrat.recognizers import recognizers_for_store
from pseudokrat.store.profile import ProfileManager
from pseudokrat.store.secure_db import InvalidPasswordError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 31337
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_TEXTS_PER_REQUEST = 1_000
MAX_TEXT_CHARS = 2_000_000
MAX_TOTAL_TEXT_CHARS = 4_000_000
ALLOWED_ORIGINS = (
    "https://127.0.0.1",
    "https://localhost",
    "https://excel.officeapps.live.com",
    "https://outlook.office.com",
)

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_OFFICE_ORIGIN_HOSTS = frozenset({"excel.officeapps.live.com", "outlook.office.com"})

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
        self._lock = threading.Lock()

    @staticmethod
    def _is_valid(token: str) -> bool:
        return _TOKEN_RE.fullmatch(token) is not None

    def _read_existing(self) -> str | None:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            return None
        if os.name != "nt" and info.st_mode & 0o077:
            self.path.chmod(0o600)
        try:
            token = self.path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            return None
        return token if self._is_valid(token) else None

    def _write_private(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".server-token-", dir=str(self.path.parent))
        tmp_path = Path(tmp_name)
        try:
            fchmod = getattr(os, "fchmod", None)
            if fchmod is not None:
                fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="ascii", newline="") as handle:
                fd = -1
                handle.write(token)
                handle.flush()
                os.fsync(handle.fileno())
            tmp_path.replace(self.path)
            self.path.chmod(0o600)
        finally:
            if fd >= 0:
                os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()

    def ensure(self) -> str:
        with self._lock:
            if self._token is not None:
                return self._token
            token = self._read_existing()
            if token is None:
                token = secrets.token_urlsafe(32)
                self._write_private(token)
            self._token = token
            return token


@dataclass
class ServerState:
    profile_manager: ProfileManager
    profile_name: str
    password: str
    token_store: TokenStore
    no_ml: bool = False
    rate_limiter: TokenBucket = field(default_factory=bucket_from_env)
    _store: object | None = field(default=None, init=False, repr=False)

    def open_session(
        self,
    ) -> tuple[Anonymizer, Deanonymizer]:
        from pseudokrat.store.mapping_store import MappingStore

        store, audit = self.profile_manager.open_or_create(self.profile_name, self.password)
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
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or parsed.hostname is None
    ):
        return None
    hostname = parsed.hostname.casefold()
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        return origin
    if hostname in _OFFICE_ORIGIN_HOSTS and port in (None, 443):
        return origin
    return None


class _InvalidRequestBodyError(ValueError):
    pass


class _RequestBodyTooLargeError(_InvalidRequestBodyError):
    pass


class _RequestHandler(BaseHTTPRequestHandler):
    state: ServerState  # injected by make_handler

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Logging über structlog, nicht stderr-Direct-Print."""
        from pseudokrat.logging_config import get_logger

        get_logger("pseudokrat.server").info("http", method=self.command, path=self.path, args=args)

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

    def _send_json(
        self,
        status: int,
        payload: object,
        *,
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra_headers:
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
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _InvalidRequestBodyError("missing-content-length")
        try:
            length = int(raw_length, 10)
        except ValueError as exc:
            raise _InvalidRequestBodyError("invalid-content-length") from exc
        if length <= 0:
            raise _InvalidRequestBodyError("empty-body")
        if length > MAX_REQUEST_BYTES:
            raise _RequestBodyTooLargeError("request-too-large")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise _InvalidRequestBodyError("incomplete-body")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _InvalidRequestBodyError("invalid-json") from exc
        if not isinstance(data, dict):
            raise _InvalidRequestBodyError("json-object-required")
        return data

    # ----- routes -----------------------------------------------------------

    def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP-Server-API
        self._send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802 - HTTP-Server-API
        if self.path == "/health":
            if not self._require_token():
                return
            profiles = [p.name for p in self.state.profile_manager.list_profiles()]
            self._send_json(200, {"version": __version__, "profiles": profiles})
            return
        self._send_json(404, {"error": "not-found"})

    def do_POST(self) -> None:  # noqa: N802 - HTTP-Server-API
        if not self._require_token():
            return
        if self.path in ("/v1/anonymize", "/v1/deanonymize"):
            decision = self.state.rate_limiter.try_consume()
            if not decision.allowed:
                # Retry-After als ganze Sekunden, aufgerundet, min 1.
                from math import ceil

                retry_after = max(1, ceil(decision.retry_after_seconds))
                self._send_json(
                    429,
                    {"error": "rate-limited"},
                    extra_headers=(("Retry-After", str(retry_after)),),
                )
                return
            try:
                body = self._read_body()
            except _RequestBodyTooLargeError as exc:
                self._send_json(413, {"error": str(exc)})
                return
            except _InvalidRequestBodyError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            texts_raw = body.get("texts")
            if not isinstance(texts_raw, list):
                self._send_json(400, {"error": "texts-must-be-list"})
                return
            if len(texts_raw) > MAX_TEXTS_PER_REQUEST:
                self._send_json(413, {"error": "too-many-texts"})
                return
            if not all(isinstance(t, str) for t in texts_raw):
                self._send_json(400, {"error": "texts-must-contain-strings"})
                return
            texts = list(texts_raw)
            if any(len(t) > MAX_TEXT_CHARS for t in texts):
                self._send_json(413, {"error": "text-too-large"})
                return
            if sum(map(len, texts)) > MAX_TOTAL_TEXT_CHARS:
                self._send_json(413, {"error": "total-text-too-large"})
                return
            try:
                anonymizer, deanonymizer = self.state.open_session()
                try:
                    if self.path.endswith("/anonymize"):
                        results = [
                            {"input": t, "output": anonymizer.anonymize(t).text} for t in texts
                        ]
                    else:
                        results = [
                            {"input": t, "output": deanonymizer.deanonymize(t).text} for t in texts
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
    normalized_host = host.strip().strip("[]").casefold()
    if normalized_host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Der Pseudokrat-Server darf nur an eine Loopback-Adresse binden.")
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
