"""Tests für den optionalen Hotkey-Daemon."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import cast

import pytest

from pseudokrat.hotkey import (
    HotkeyBackend,
    HotkeyConfig,
    HotkeyDaemon,
    HotkeyUnavailableError,
    KeyboardBackend,
    PynputBackend,
)


class _FakeBackend:
    """In-Memory-Backend für Tests."""

    name = "fake"

    def __init__(self) -> None:
        self.registered: dict[str, Callable[[], None]] = {}
        self.run_event = threading.Event()
        self.stop_event = threading.Event()

    def register(self, combination: str, callback: Callable[[], None]) -> None:
        self.registered[combination] = callback

    def run_forever(self) -> None:
        self.run_event.set()
        self.stop_event.wait(timeout=2)

    def stop(self) -> None:
        self.stop_event.set()


def test_daemon_registers_both_hotkeys() -> None:
    backend = _FakeBackend()
    daemon = HotkeyDaemon(
        on_anonymize=lambda: None,
        on_deanonymize=lambda: None,
        backend=cast(HotkeyBackend, backend),
    )
    daemon.register()
    assert "ctrl+shift+a" in backend.registered
    assert "ctrl+shift+d" in backend.registered


def test_daemon_custom_hotkeys() -> None:
    backend = _FakeBackend()
    daemon = HotkeyDaemon(
        on_anonymize=lambda: None,
        on_deanonymize=lambda: None,
        config=HotkeyConfig(anonymize="alt+1", deanonymize="alt+2"),
        backend=cast(HotkeyBackend, backend),
    )
    daemon.register()
    assert "alt+1" in backend.registered
    assert "alt+2" in backend.registered


def test_callbacks_are_invoked_via_backend() -> None:
    backend = _FakeBackend()
    calls: list[str] = []
    daemon = HotkeyDaemon(
        on_anonymize=lambda: calls.append("anon"),
        on_deanonymize=lambda: calls.append("deanon"),
        backend=cast(HotkeyBackend, backend),
    )
    daemon.register()
    backend.registered["ctrl+shift+a"]()
    backend.registered["ctrl+shift+d"]()
    assert calls == ["anon", "deanon"]


def test_daemon_run_forever_blocks_then_stops() -> None:
    backend = _FakeBackend()
    daemon = HotkeyDaemon(
        on_anonymize=lambda: None,
        on_deanonymize=lambda: None,
        backend=cast(HotkeyBackend, backend),
    )

    t = threading.Thread(target=daemon.run_forever, daemon=True)
    t.start()
    assert backend.run_event.wait(timeout=2)
    daemon.stop()
    t.join(timeout=2)
    assert not t.is_alive()


def test_keyboard_backend_raises_when_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "keyboard", None)
    with pytest.raises(HotkeyUnavailableError) as exc:
        KeyboardBackend()
    assert "keyboard" in str(exc.value)


def test_pynput_backend_raises_when_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "pynput", None)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", None)
    with pytest.raises(HotkeyUnavailableError) as exc:
        PynputBackend()
    assert "pynput" in str(exc.value)


def test_pynput_combo_translation() -> None:
    assert PynputBackend._to_pynput_format("ctrl+shift+a") == "<ctrl>+<shift>+a"
    assert PynputBackend._to_pynput_format("alt+1") == "<alt>+1"
    assert PynputBackend._to_pynput_format("CMD+K") == "<cmd>+k"


def test_make_clipboard_callback_reads_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pseudokrat import clipboard as clip_mod
    from pseudokrat.hotkey import make_clipboard_callback

    box = clip_mod.InMemoryClipboard()
    box.write("hallo welt")
    monkeypatch.setattr(clip_mod, "default_clipboard", lambda: box)

    cb = make_clipboard_callback(lambda t: t.upper())
    cb()
    assert box.read() == "HALLO WELT"


def test_make_clipboard_callback_skips_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from pseudokrat import clipboard as clip_mod
    from pseudokrat.hotkey import make_clipboard_callback

    box = clip_mod.InMemoryClipboard()
    box.write("")
    monkeypatch.setattr(clip_mod, "default_clipboard", lambda: box)

    transformed: list[str] = []
    cb = make_clipboard_callback(lambda t: (transformed.append(t), t)[1])
    cb()
    assert transformed == []
