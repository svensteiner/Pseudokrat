"""Optionaler globaler Hotkey-Daemon (§3 Workflow A des Megaprompts).

Pseudokrat startet selbst keinen Hotkey-Listener (D-024) — der empfohlene
Pfad bleibt OS-Hotkey-Tool + CLI-Subbefehl ``pseudokrat clipboard ...``.

Wer trotzdem einen integrierten Daemon will, kann das Modul hier
verwenden. Es bietet:

* :class:`HotkeyDaemon` mit Start/Stop und Logging.
* Konfigurierbare Hotkey-Strings (Default: ``Strg+Shift+A`` und
  ``Strg+Shift+D``).
* Plattform-Adapter via ``keyboard`` (Windows; benötigt Admin) und
  ``pynput`` (macOS/Linux; benötigt Accessibility-Freigabe).

CLI-Einbindung: ``pseudokrat hotkey-daemon --profile ... --password ...``.
Das Tool blockt im Vordergrund und reagiert auf Ctrl-C.

Beide Bibliotheken sind als optionales Extra ``pseudokrat[hotkeys]``
deklariert; ohne sie schlägt der Start mit klarer Fehlermeldung fehl —
kein Silent-Skip.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pseudokrat.clipboard import ClipboardUnavailableError


class HotkeyUnavailableError(RuntimeError):
    """Hotkey-Backend fehlt oder konnte nicht registriert werden."""


@dataclass
class HotkeyConfig:
    anonymize: str = "ctrl+shift+a"
    deanonymize: str = "ctrl+shift+d"


@dataclass
class HotkeyEvent:
    action: str  # "anonymize" | "deanonymize"


class HotkeyBackend(Protocol):
    """Adapter-Interface für die Plattform-spezifischen Bibliotheken."""

    name: str

    def register(self, combination: str, callback: Callable[[], None]) -> None: ...
    def run_forever(self) -> None: ...
    def stop(self) -> None: ...


class KeyboardBackend:
    """Adapter für die `keyboard`-Library (Windows-Fokus)."""

    name = "keyboard"

    def __init__(self) -> None:
        try:
            import keyboard  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            raise HotkeyUnavailableError(
                "Die `keyboard`-Library ist nicht installiert. "
                "Installation: `pip install pseudokrat[hotkeys]`."
            ) from exc
        self._lib = keyboard
        self._stop_event = threading.Event()

    def register(self, combination: str, callback: Callable[[], None]) -> None:
        self._lib.add_hotkey(combination, callback)

    def run_forever(self) -> None:
        # `keyboard.wait()` blockt — wir nutzen den Stop-Event als Abbruch.
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self._lib.unhook_all()

    def stop(self) -> None:
        self._stop_event.set()


class PynputBackend:
    """Adapter für `pynput` (macOS + Linux + Windows)."""

    name = "pynput"

    def __init__(self) -> None:
        try:
            from pynput import keyboard  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:
            raise HotkeyUnavailableError(
                "Die `pynput`-Library ist nicht installiert. "
                "Installation: `pip install pseudokrat[hotkeys]`."
            ) from exc
        self._listener_cls = keyboard.GlobalHotKeys
        self._hotkeys: dict[str, Callable[[], None]] = {}
        self._listener: object | None = None

    @staticmethod
    def _to_pynput_format(combo: str) -> str:
        """`keyboard`-Stil → `pynput`-Stil.

        Beispiel: ``"ctrl+shift+a"`` → ``"<ctrl>+<shift>+a"``.
        """
        special = {"ctrl", "shift", "alt", "cmd", "meta", "super"}
        parts = combo.lower().split("+")
        return "+".join(f"<{p}>" if p in special else p for p in parts)

    def register(self, combination: str, callback: Callable[[], None]) -> None:
        self._hotkeys[self._to_pynput_format(combination)] = callback

    def run_forever(self) -> None:
        listener = self._listener_cls(self._hotkeys)
        self._listener = listener
        listener.run()  # type: ignore[attr-defined,unused-ignore]

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()  # type: ignore[attr-defined,unused-ignore]


def select_backend() -> HotkeyBackend:
    """Liefere das beste verfügbare Backend für die aktuelle Plattform."""
    errors: list[str] = []
    if sys.platform == "win32":
        try:
            return KeyboardBackend()
        except HotkeyUnavailableError as exc:
            errors.append(str(exc))
    try:
        return PynputBackend()
    except HotkeyUnavailableError as exc:
        errors.append(str(exc))
    if sys.platform == "win32" or "KeyboardBackend" not in str(errors):
        try:
            return KeyboardBackend()
        except HotkeyUnavailableError as exc:
            errors.append(str(exc))
    raise HotkeyUnavailableError("Kein Hotkey-Backend verfügbar:\n" + "\n".join(errors))


@dataclass
class HotkeyDaemon:
    """Bindet zwei globale Hotkeys an Anonymize/Deanonymize-Callbacks.

    Die Callbacks (typischerweise CLI-Wrapper) müssen idempotent und
    threadsicher sein — Hotkey-Backends rufen sie aus eigenen Threads
    auf.
    """

    on_anonymize: Callable[[], None]
    on_deanonymize: Callable[[], None]
    config: HotkeyConfig = field(default_factory=HotkeyConfig)
    backend: HotkeyBackend | None = None

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = select_backend()

    def register(self) -> None:
        assert self.backend is not None
        self.backend.register(self.config.anonymize, self.on_anonymize)
        self.backend.register(self.config.deanonymize, self.on_deanonymize)

    def run_forever(self) -> None:
        assert self.backend is not None
        self.register()
        self.backend.run_forever()

    def stop(self) -> None:
        assert self.backend is not None
        self.backend.stop()


def make_clipboard_callback(action: Callable[[str], str]) -> Callable[[], None]:
    """Helper: Hotkey → Read clipboard → action → Write clipboard.

    Tests können diesen Wrapper mit einer In-Memory-Clipboard testen,
    indem sie ``pseudokrat.clipboard.default_clipboard`` monkeypatchen.
    Der Import erfolgt deshalb erst beim Callback-Aufruf.
    """

    def _run() -> None:
        from pseudokrat import clipboard as clip_mod

        try:
            clip = clip_mod.default_clipboard()
            text = clip.read()
            if not text:
                return
            clip.write(action(text))
        except ClipboardUnavailableError:
            return

    return _run
