"""Tests für das Zwischenablage-Modul (`pseudokrat.clipboard`)."""

from __future__ import annotations

import pytest

from pseudokrat.clipboard import (
    Clipboard,
    ClipboardUnavailableError,
    InMemoryClipboard,
    PyperclipClipboard,
)


def test_inmemory_clipboard_round_trip() -> None:
    cb = InMemoryClipboard()
    assert cb.read() == ""
    cb.write("Hallo Welt")
    assert cb.read() == "Hallo Welt"
    cb.write("ersetzt")
    assert cb.read() == "ersetzt"


def test_inmemory_clipboard_initial_value() -> None:
    cb = InMemoryClipboard(initial="vorbelegt")
    assert cb.read() == "vorbelegt"


def test_inmemory_clipboard_implements_protocol() -> None:
    cb: Clipboard = InMemoryClipboard()
    cb.write("x")
    assert cb.read() == "x"


def test_pyperclip_clipboard_reads_and_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter delegiert sauber an das `pyperclip`-Modul."""

    state = {"buffer": "initial"}

    class FakePyperclip:
        @staticmethod
        def paste() -> str:
            return state["buffer"]

        @staticmethod
        def copy(text: str) -> None:
            state["buffer"] = text

    fake = FakePyperclip()
    monkeypatch.setitem(__import__("sys").modules, "pyperclip", fake)

    cb = PyperclipClipboard()
    assert cb.read() == "initial"
    cb.write("neu")
    assert state["buffer"] == "neu"
    assert cb.read() == "neu"


def test_pyperclip_clipboard_paste_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pyperclip.paste()` kann unter manchen OS `None` liefern — wir geben "" zurück."""

    class FakePyperclip:
        @staticmethod
        def paste() -> None:
            return None

        @staticmethod
        def copy(text: str) -> None:
            pass

    monkeypatch.setitem(__import__("sys").modules, "pyperclip", FakePyperclip())

    cb = PyperclipClipboard()
    assert cb.read() == ""


def test_clipboard_unavailable_error_is_runtime_error() -> None:
    err = ClipboardUnavailableError("test")
    assert isinstance(err, RuntimeError)
    assert str(err) == "test"
