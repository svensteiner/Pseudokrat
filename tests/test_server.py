"""Smoke-Tests für den lokalen HTTP-Server (Office-Add-in-Backend)."""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

import pytest

from pseudokrat.server import (
    DEFAULT_HOST,
    ServerState,
    TokenStore,
    _origin_allowed,
    start_server,
)
from pseudokrat.store.profile import ProfileManager


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def running_server(tmp_path: Path) -> ServerState:
    return ServerState(
        profile_manager=ProfileManager(),
        profile_name="default",
        password="supergeheim",
        token_store=TokenStore(tmp_path / "token.txt"),
        no_ml=True,
    )


def test_token_store_persists_token(tmp_path: Path) -> None:
    path = tmp_path / "token.txt"
    store = TokenStore(path)
    a = store.ensure()
    assert path.read_text(encoding="ascii").strip() == a
    # Zweite Instanz liest denselben Token zurück.
    b = TokenStore(path).ensure()
    assert b == a


def test_origin_allowed() -> None:
    assert _origin_allowed("https://127.0.0.1:31337") == "https://127.0.0.1:31337"
    assert _origin_allowed("https://localhost:31337") == "https://localhost:31337"
    assert _origin_allowed("https://excel.officeapps.live.com") is not None
    assert _origin_allowed("https://böses-tab.example.com") is None
    assert _origin_allowed(None) is None


def test_health_endpoint_returns_version_and_profiles(running_server: ServerState) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/health",
            headers={"Authorization": f"Bearer {running_server.token_store.ensure()}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost
            payload = json.loads(resp.read().decode("utf-8"))
        assert "version" in payload
        assert "profiles" in payload
    finally:
        server.stop()


def test_anonymize_endpoint_requires_token(running_server: ServerState) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/v1/anonymize",
            data=json.dumps({"texts": ["Hofer Bau GmbH"], "profile": "default"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)  # noqa: S310 - localhost
        assert exc.value.code == 401
    finally:
        server.stop()


def test_anonymize_endpoint_with_valid_token_returns_results(
    running_server: ServerState,
) -> None:
    # Profil muss existieren, bevor der Server es öffnet.
    running_server.profile_manager.open_or_create("default", "supergeheim")
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        token = running_server.token_store.ensure()
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/v1/anonymize",
            data=json.dumps({"texts": ["Hofer Bau GmbH"], "profile": "default"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost
            payload = json.loads(resp.read().decode("utf-8"))
        assert len(payload["results"]) == 1
        assert "<COMPANY_001>" in payload["results"][0]["output"]
    finally:
        server.stop()


def test_health_response_includes_security_headers(running_server: ServerState) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/health",
            headers={"Authorization": f"Bearer {running_server.token_store.ensure()}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost
            headers = {k.lower(): v for k, v in resp.getheaders()}
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("referrer-policy") == "no-referrer"
        assert headers.get("cross-origin-resource-policy") == "same-origin"
        csp = headers.get("content-security-policy", "")
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "no-store" in headers.get("cache-control", "")
        assert headers.get("vary") == "Origin"
    finally:
        server.stop()


def test_options_preflight_includes_allow_headers_for_allowed_origin(
    running_server: ServerState,
) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/v1/anonymize",
            method="OPTIONS",
            headers={
                "Origin": "https://excel.officeapps.live.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost
            headers = {k.lower(): v for k, v in resp.getheaders()}
        # Preflight aus erlaubter Origin → CORS-Header gespiegelt + Max-Age.
        assert headers.get("access-control-allow-origin") == "https://excel.officeapps.live.com"
        assert "POST" in headers.get("access-control-allow-methods", "")
        assert headers.get("access-control-max-age") == "600"
        # Defense-in-depth: Security-Header auch auf 204 mit dabei.
        assert headers.get("x-frame-options") == "DENY"
    finally:
        server.stop()


def test_options_from_disallowed_origin_drops_cors_headers(
    running_server: ServerState,
) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        req = urllib.request.Request(
            f"http://{DEFAULT_HOST}:{port}/v1/anonymize",
            method="OPTIONS",
            headers={"Origin": "https://böses-tab.example.com"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 - localhost
            headers = {k.lower(): v for k, v in resp.getheaders()}
        # Eine Disallowed Origin darf NICHT in `Access-Control-Allow-Origin` landen.
        assert "access-control-allow-origin" not in headers
        # Vary muss trotzdem stehen — verhindert Cache-Poisoning via fehlende Origin-Variation.
        assert headers.get("vary") == "Origin"
    finally:
        server.stop()


def test_unknown_path_returns_404(running_server: ServerState) -> None:
    port = _free_port()
    server = start_server(running_server, host=DEFAULT_HOST, port=port, in_background=True)
    try:
        with pytest.raises(HTTPError) as exc:
            urllib.request.urlopen(  # noqa: S310 - localhost
                f"http://{DEFAULT_HOST}:{port}/nope", timeout=5
            )
        assert exc.value.code == 404
    finally:
        server.stop()
