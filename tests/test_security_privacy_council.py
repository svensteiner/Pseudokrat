"""Focused regressions for local privacy and fail-closed boundaries."""

from __future__ import annotations

import http.client
import zipfile
from pathlib import Path

import pytest

from pseudokrat import watcher
from pseudokrat.formats.base import UnsafeArchiveError, validate_office_archive
from pseudokrat.pii.ollama_detector import _validate_local_url
from pseudokrat.server import (
    DEFAULT_HOST,
    MAX_REQUEST_BYTES,
    ServerState,
    TokenStore,
    _origin_allowed,
    start_server,
)
from pseudokrat.store.mapping_store import MappingStore
from pseudokrat.store.profile import ProfileManager
from pseudokrat.store.secure_db import InvalidPasswordError


def test_cors_origin_matching_rejects_prefix_confusion() -> None:
    assert _origin_allowed("https://localhost:31337") is not None
    assert _origin_allowed("https://excel.officeapps.live.com") is not None
    assert _origin_allowed("https://localhost.evil.example") is None
    assert _origin_allowed("https://excel.officeapps.live.com.evil.example") is None
    assert _origin_allowed("https://excel.officeapps.live.com:444") is None
    assert _origin_allowed("https://user@localhost") is None


def test_ollama_urls_are_loopback_only() -> None:
    _validate_local_url("http://localhost:11434/api/generate")
    _validate_local_url("http://127.0.0.1:11434/api/generate")
    _validate_local_url("http://[::1]:11434/api/generate")
    with pytest.raises(ValueError):
        _validate_local_url("https://ollama.example.com/api/generate")
    with pytest.raises(ValueError):
        _validate_local_url("file:///etc/passwd")


def test_server_refuses_non_loopback_bind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    state = ServerState(
        profile_manager=ProfileManager(),
        profile_name="default",
        password="test-password",
        token_store=TokenStore(tmp_path / "token.txt"),
        no_ml=True,
    )
    with pytest.raises(ValueError, match="Loopback"):
        start_server(state, host="0.0.0.0", port=0)


def test_server_health_requires_bearer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    state = ServerState(
        profile_manager=ProfileManager(),
        profile_name="default",
        password="test-password",
        token_store=TokenStore(tmp_path / "token.txt"),
        no_ml=True,
    )
    server = start_server(state, host=DEFAULT_HOST, port=0)
    port = int(server.httpd.server_address[1])
    try:
        conn = http.client.HTTPConnection(DEFAULT_HOST, port, timeout=30)
        conn.request("GET", "/health")
        response = conn.getresponse()
        assert response.status == 401
        response.read()
        conn.close()
    finally:
        server.stop()


def test_server_rejects_oversized_body_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    state = ServerState(
        profile_manager=ProfileManager(),
        profile_name="default",
        password="test-password",
        token_store=TokenStore(tmp_path / "token.txt"),
        no_ml=True,
    )
    server = start_server(state, host=DEFAULT_HOST, port=0)
    port = int(server.httpd.server_address[1])
    try:
        conn = http.client.HTTPConnection(DEFAULT_HOST, port, timeout=30)
        conn.putrequest("POST", "/v1/anonymize")
        conn.putheader("Authorization", f"Bearer {state.token_store.ensure()}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        assert response.status == 413
        response.read()
        conn.close()
    finally:
        server.stop()


def test_malformed_persisted_server_token_is_rotated(tmp_path: Path) -> None:
    path = tmp_path / "token.txt"
    path.write_text("weak", encoding="ascii")
    token = TokenStore(path).ensure()
    assert token != "weak"
    assert len(token) >= 43
    assert path.read_text(encoding="ascii") == token


def test_profile_slug_collision_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    manager = ProfileManager()
    store, _ = manager.open_or_create("A B", "same-password")
    store.close()
    with pytest.raises(ValueError, match="kollidiert"):
        manager.open_or_create("A_B", "same-password")


def test_profile_db_must_be_regular_file(tmp_path: Path) -> None:
    db_path = tmp_path / "profile.sqlite"
    db_path.mkdir()
    with pytest.raises(InvalidPasswordError, match="reguläre Datei"):
        MappingStore(db_path, password="password")


def test_office_archive_rejects_traversal_member(tmp_path: Path) -> None:
    path = tmp_path / "hostile.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../outside.xml", "secret")
    with pytest.raises(UnsafeArchiveError, match="unsicheren Pfad"):
        validate_office_archive(path)


def test_gate_extraction_error_is_not_treated_as_clean(tmp_path: Path) -> None:
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not-a-zip")
    with pytest.raises(watcher.OutputInspectionError):
        watcher.extract_text_for_gate(broken)


def test_scan_ignores_symlinked_input(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("sensitive", encoding="utf-8")
    inbox = tmp_path / "INPUT"
    inbox.mkdir()
    link = inbox / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks require additional privileges on this platform")
    assert watcher._scan(inbox) == []
