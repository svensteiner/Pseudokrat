"""Zwischenablage-Anbindung für den Hotkey-Workflow (§3 Workflow A).

Der Hotkey-Pfad bindet keinen globalen Tastatur-Listener in den Prozess ein
(``keyboard`` benötigt Admin-Rechte unter Windows, ``pynput`` Accessibility-
Berechtigung unter macOS). Stattdessen liefert Pseudokrat einen CLI-Subbefehl
``pseudokrat clipboard {anonymize,deanonymize}``, den der Nutzer über sein
bevorzugtes OS-Hotkey-Werkzeug (PowerToys, AutoHotkey, macOS Shortcuts) auf
``Strg+Shift+A`` bzw. ``Strg+Shift+D`` legt.

Dieses Modul kapselt die System-Zwischenablage hinter einem :class:`Clipboard`-
Protokoll. Die Default-Implementierung verwendet ``pyperclip`` (optionale
Abhängigkeit). Für Tests und headless-Pfade existiert :class:`InMemoryClipboard`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ClipboardUnavailableError(RuntimeError):
    """Wird geworfen, wenn die Systemzwischenablage nicht zugänglich ist.

    Mögliche Ursachen: ``pyperclip`` nicht installiert, kein Display-Server
    (z. B. headless Linux ohne xclip), oder das System verweigert den Zugriff.
    """


@runtime_checkable
class Clipboard(Protocol):
    """Minimale Zwischenablage-API: read/write Text."""

    def read(self) -> str: ...

    def write(self, text: str) -> None: ...


class InMemoryClipboard:
    """In-Process-Zwischenablage — für Tests und headless-Skripte.

    Verhält sich wie eine echte Zwischenablage, lebt aber nur im Speicher
    der aktuellen Python-Prozesses.
    """

    def __init__(self, initial: str = "") -> None:
        self._content = initial

    def read(self) -> str:
        return self._content

    def write(self, text: str) -> None:
        self._content = text


class PyperclipClipboard:
    """Adapter um ``pyperclip``.

    Das Paket wird lazy importiert, damit Pseudokrat ohne ``pyperclip``
    installierbar bleibt (z. B. auf reinen Server-Setups, in denen nur die
    Datei-Pipeline benötigt wird).
    """

    def __init__(self) -> None:
        try:
            import pyperclip
        except ImportError as exc:  # pragma: no cover - hängt von der Umgebung ab
            raise ClipboardUnavailableError(
                "Das Paket 'pyperclip' ist nicht installiert. Bitte "
                "`pip install pseudokrat[clipboard]` ausführen."
            ) from exc
        self._pyperclip = pyperclip

    def read(self) -> str:
        try:
            value = self._pyperclip.paste()
        except Exception as exc:  # pragma: no cover - OS-spezifischer Fehlerpfad
            raise ClipboardUnavailableError(
                f"Zwischenablage konnte nicht gelesen werden: {exc}"
            ) from exc
        return "" if value is None else str(value)

    def write(self, text: str) -> None:
        try:
            self._pyperclip.copy(text)
        except Exception as exc:  # pragma: no cover - OS-spezifischer Fehlerpfad
            raise ClipboardUnavailableError(
                f"Zwischenablage konnte nicht beschrieben werden: {exc}"
            ) from exc


def default_clipboard() -> Clipboard:
    """Standard-Factory: System-Zwischenablage via ``pyperclip``.

    Tests monkeypatchen diese Funktion und liefern eine
    :class:`InMemoryClipboard` zurück.
    """
    return PyperclipClipboard()


__all__ = [
    "Clipboard",
    "ClipboardUnavailableError",
    "InMemoryClipboard",
    "PyperclipClipboard",
    "default_clipboard",
]
