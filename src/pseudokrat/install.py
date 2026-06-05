"""Windows-Integration: Explorer-Context-Menu + Autostart.

Phase-B-Vereinfachung — ein Befehl, der Pseudokrat in den Workflow eines
Berufsträgers einbettet:

* Rechtsklick auf `.pdf`/`.docx`/`.xlsx`/`.csv`/`.txt` im Explorer →
  „Mit Pseudokrat anonymisieren". Schreibt die anonymisierte Kopie neben
  das Original (`datei.anon.pdf`).
* Optional: Hotkey-Daemon beim Login automatisch starten
  (`--with-hotkeys`).

Alle Eintragungen liegen unter ``HKCU\\Software\\Classes\\...`` bzw.
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` — **keine
Admin-Rechte nötig**, gilt nur für den aktuellen Benutzer. Das macht
den Installer für DACH-Kanzleien tauglich, wo IT-Policies oft jeden
Admin-Schritt blockieren.

Test-Strategie: alle Registry-Zugriffe gehen durch das
``RegistryBackend``-Protocol. Production nutzt :class:`WinRegistryBackend`
(``winreg``-Stdlib, Windows-only). Tests injizieren
:class:`InMemoryRegistryBackend` — damit läuft die Suite auch unter
Linux/macOS-CI.
"""

from __future__ import annotations

import contextlib
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# ---------- Konstanten ------------------------------------------------------

#: Liste der Dateierweiterungen, für die der Explorer-Eintrag registriert wird.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".xlsx", ".csv", ".txt")

#: Sichtbarer Eintrag im Rechtsklick-Menü.
CONTEXT_MENU_LABEL = "Mit Pseudokrat anonymisieren"

#: Interner Subkey-Name (kein Sonderzeichen, damit der Registry-Pfad sauber bleibt).
CONTEXT_MENU_KEY = "PseudokratAnonymize"

#: Autostart-Eintrag-Name (HKCU\...\Run).
AUTOSTART_RUN_NAME = "PseudokratHotkeyDaemon"

#: Service-Name für den OS-Keyring beim Default-Profil-Setup.
DEFAULT_PROFILE_NAME = "Mein Konto"


# ---------- Registry-Abstraktion --------------------------------------------


class RegistryBackend(Protocol):
    """Minimale Registry-API: Stringwert lesen/schreiben/löschen, Subkey-
    Existenz prüfen. Ausreichend für unseren Use-Case (kein REG_BINARY etc.)."""

    def set_string(self, hive: str, subkey: str, name: str, value: str) -> None: ...

    def get_string(self, hive: str, subkey: str, name: str) -> str | None: ...

    def delete_value(self, hive: str, subkey: str, name: str) -> None: ...

    def delete_tree(self, hive: str, subkey: str) -> None: ...

    def subkey_exists(self, hive: str, subkey: str) -> bool: ...


class WinRegistryBackend:
    """Windows-Implementation via stdlib ``winreg``.

    Lazy-Import, damit das Modul auf macOS/Linux importierbar bleibt
    (z. B. für Unit-Tests gegen den Stub-Backend).
    """

    @staticmethod
    def _winreg() -> Any:
        try:
            import winreg  # type: ignore[import-not-found,unused-ignore]
        except ImportError as exc:  # pragma: no cover - non-Windows path
            raise RuntimeError(
                "Explorer-Context-Menu ist nur unter Windows verfügbar."
            ) from exc
        return winreg

    @staticmethod
    def _hkey(winreg_mod: Any, hive: str) -> int:
        mapping = {
            "HKCU": winreg_mod.HKEY_CURRENT_USER,
            "HKLM": winreg_mod.HKEY_LOCAL_MACHINE,
        }
        if hive not in mapping:
            raise ValueError(f"Unbekanntes Hive: {hive}")
        return int(mapping[hive])

    def set_string(self, hive: str, subkey: str, name: str, value: str) -> None:
        winreg = self._winreg()
        hkey = self._hkey(winreg, hive)
        key = winreg.CreateKeyEx(hkey, subkey, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(key)

    def get_string(self, hive: str, subkey: str, name: str) -> str | None:
        winreg = self._winreg()
        hkey = self._hkey(winreg, hive)
        try:
            key = winreg.OpenKeyEx(hkey, subkey, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return None
        try:
            try:
                value, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                return None
        finally:
            winreg.CloseKey(key)
        return str(value)

    def delete_value(self, hive: str, subkey: str, name: str) -> None:
        winreg = self._winreg()
        hkey = self._hkey(winreg, hive)
        try:
            key = winreg.OpenKeyEx(hkey, subkey, 0, winreg.KEY_SET_VALUE)
        except FileNotFoundError:
            return
        try:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, name)
        finally:
            winreg.CloseKey(key)

    def delete_tree(self, hive: str, subkey: str) -> None:
        """Rekursives Löschen eines Subkey-Baums (Win Vista+).

        Idempotent: wenn der Subkey nicht existiert, wird kein Fehler
        ausgelöst.
        """
        winreg = self._winreg()
        hkey = self._hkey(winreg, hive)
        # winreg.DeleteKeyEx mit Wildcard gibt es nicht — wir gehen rekursiv.
        with contextlib.suppress(FileNotFoundError):
            self._delete_subkey_recursive(winreg, hkey, subkey)

    def _delete_subkey_recursive(self, winreg: Any, root_hkey: int, subkey: str) -> None:
        # Öffne Subkey, enumeriere Kinder, lösche bottom-up.
        try:
            key = winreg.OpenKeyEx(root_hkey, subkey, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return
        try:
            children: list[str] = []
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                children.append(name)
                i += 1
        finally:
            winreg.CloseKey(key)
        for child in children:
            self._delete_subkey_recursive(winreg, root_hkey, f"{subkey}\\{child}")
        with contextlib.suppress(FileNotFoundError):
            winreg.DeleteKey(root_hkey, subkey)

    def subkey_exists(self, hive: str, subkey: str) -> bool:
        winreg = self._winreg()
        hkey = self._hkey(winreg, hive)
        try:
            key = winreg.OpenKeyEx(hkey, subkey, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return False
        winreg.CloseKey(key)
        return True


@dataclass
class InMemoryRegistryBackend:
    """Test-Backend. Bildet Subkeys als verschachtelte Dicts ab."""

    _store: dict[str, dict[str, dict[str, str]]] = field(
        default_factory=lambda: {"HKCU": {}, "HKLM": {}}
    )

    def _ensure_hive(self, hive: str) -> dict[str, dict[str, str]]:
        if hive not in self._store:
            raise ValueError(f"Unbekanntes Hive: {hive}")
        return self._store[hive]

    def set_string(self, hive: str, subkey: str, name: str, value: str) -> None:
        hive_dict = self._ensure_hive(hive)
        hive_dict.setdefault(subkey, {})[name] = value

    def get_string(self, hive: str, subkey: str, name: str) -> str | None:
        hive_dict = self._ensure_hive(hive)
        return hive_dict.get(subkey, {}).get(name)

    def delete_value(self, hive: str, subkey: str, name: str) -> None:
        hive_dict = self._ensure_hive(hive)
        hive_dict.get(subkey, {}).pop(name, None)

    def delete_tree(self, hive: str, subkey: str) -> None:
        hive_dict = self._ensure_hive(hive)
        prefix = subkey
        for k in list(hive_dict.keys()):
            if k == prefix or k.startswith(prefix + "\\"):
                del hive_dict[k]

    def subkey_exists(self, hive: str, subkey: str) -> bool:
        hive_dict = self._ensure_hive(hive)
        return subkey in hive_dict or any(
            k.startswith(subkey + "\\") for k in hive_dict
        )


# ---------- Befehls-Resolution ----------------------------------------------


def resolve_pseudokrat_command() -> str:
    """Liefert die Kommandozeile zum Aufruf von Pseudokrat — als Registry-
    REG_SZ-Wert mit Platzhalter ``%1`` für die anvisierte Datei.

    Reihenfolge:

    1. Wenn ``pseudokrat.exe`` im PATH liegt (PyInstaller-Build oder
       Scripts-Verzeichnis) → diesen Pfad direkt.
    2. Sonst: ``"<python.exe>" -m pseudokrat`` (dev-install).

    Pfade werden korrekt für REG_SZ gequotet (innere ``"`` werden zu
    ``""`` verdoppelt — das ist die übliche Convention für Windows-
    Kommandozeilen).
    """
    exe = shutil.which("pseudokrat")
    if exe is not None:
        return f'"{exe}" anonymize --input "%1"'
    python = sys.executable
    return f'"{python}" -m pseudokrat anonymize --input "%1"'


def resolve_hotkey_daemon_command(profile: str) -> str:
    """Kommandozeile für Hotkey-Autostart. Profil als expliziter Parameter,
    damit der Daemon nicht raten muss, welches Profil aktiv ist."""
    exe = shutil.which("pseudokrat")
    if exe is not None:
        return f'"{exe}" hotkey-daemon --profile "{profile}"'
    python = sys.executable
    return f'"{python}" -m pseudokrat hotkey-daemon --profile "{profile}"'


# ---------- Install-/Uninstall-Plumbing -------------------------------------


@dataclass(frozen=True)
class InstallResult:
    """Was ``install`` tatsächlich getan hat — fürs Reporting im CLI."""

    extensions_registered: tuple[str, ...]
    extensions_skipped: tuple[str, ...]
    autostart_registered: bool
    profile_created: bool
    profile_name: str
    notes: tuple[str, ...] = ()
    #: Wenn das Default-Profil **angefragt** war (``create_profile=True``),
    #: aber die Anlage scheiterte, steht hier der Grund. Sonst ``None``.
    #: Inline-Failure-Signal — die CLI rendert das mit ✗ statt mit einer
    #: schwachen ℹ-Note ganz unten und setzt den Exit-Code auf ungleich 0.
    profile_error: str | None = None

    @property
    def has_critical_failure(self) -> bool:
        """``True``, wenn ein vom Nutzer explizit angefragter Schritt
        scheiterte (aktuell: Profil-Anlage). Treibt den CLI-Exit-Code."""
        return self.profile_error is not None


def _context_menu_subkey(ext: str) -> str:
    """Registry-Pfad für unseren Context-Menu-Eintrag pro Extension.

    Wir hängen uns an ``SystemFileAssociations\\<.ext>\\shell\\<Key>``,
    nicht an ``HKCU\\Software\\Classes\\<.ext>\\shell\\...``. Vorteil:
    SystemFileAssociations greift unabhängig vom installierten Default-
    Handler — der Eintrag erscheint also auch dann im Rechtsklick-Menü,
    wenn der Nutzer den Default für ``.pdf`` ändert.
    """
    return f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\{CONTEXT_MENU_KEY}"


def install_context_menu(
    backend: RegistryBackend,
    *,
    extensions: tuple[str, ...] = SUPPORTED_EXTENSIONS,
    command_template: str | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Registriere den „Mit Pseudokrat anonymisieren"-Eintrag im
    Rechtsklick-Menü.

    Liefert zwei Tupel zurück: ``(registered, skipped)``. Eine Extension
    landet in ``skipped``, wenn das ``set_string`` fehlschlägt (z. B.
    Permissions) — der Rest wird weiterhin versucht.
    """
    command = command_template or resolve_pseudokrat_command()
    registered: list[str] = []
    skipped: list[str] = []
    for ext in extensions:
        base = _context_menu_subkey(ext)
        try:
            backend.set_string("HKCU", base, "", CONTEXT_MENU_LABEL)
            backend.set_string("HKCU", base, "Icon", "")  # Platzhalter — Phase C füllt Icon
            backend.set_string("HKCU", f"{base}\\command", "", command)
        except OSError:
            skipped.append(ext)
            continue
        registered.append(ext)
    return tuple(registered), tuple(skipped)


def uninstall_context_menu(
    backend: RegistryBackend,
    *,
    extensions: tuple[str, ...] = SUPPORTED_EXTENSIONS,
) -> tuple[str, ...]:
    """Entfernt unsere Einträge wieder. Idempotent — fehlende Subkeys
    werden stillschweigend ignoriert."""
    removed: list[str] = []
    for ext in extensions:
        base = _context_menu_subkey(ext)
        if backend.subkey_exists("HKCU", base):
            backend.delete_tree("HKCU", base)
            removed.append(ext)
    return tuple(removed)


def install_autostart(
    backend: RegistryBackend,
    *,
    profile: str,
    command_template: str | None = None,
) -> None:
    """Registriere den Hotkey-Daemon im Autostart (HKCU\\...\\Run).

    Idempotent: doppeltes Aufrufen überschreibt den Wert (gleicher Name
    → einziger Run-Eintrag).
    """
    command = command_template or resolve_hotkey_daemon_command(profile)
    backend.set_string(
        "HKCU",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        AUTOSTART_RUN_NAME,
        command,
    )


def uninstall_autostart(backend: RegistryBackend) -> bool:
    """Entfernt den Autostart-Eintrag. Liefert ``True``, wenn etwas
    entfernt wurde."""
    existing = backend.get_string(
        "HKCU",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        AUTOSTART_RUN_NAME,
    )
    if existing is None:
        return False
    backend.delete_value(
        "HKCU",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        AUTOSTART_RUN_NAME,
    )
    return True


def check_install_state(backend: RegistryBackend) -> dict[str, bool]:
    """Diagnose: was ist aktuell registriert?

    Liefert ein Dict ``{".pdf": True, ".docx": False, ..., "autostart": True}``
    — nützlich für ``pseudokrat install --status`` und für Tests.
    """
    state: dict[str, bool] = {}
    for ext in SUPPORTED_EXTENSIONS:
        state[ext] = backend.subkey_exists("HKCU", _context_menu_subkey(ext))
    state["autostart"] = (
        backend.get_string(
            "HKCU",
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            AUTOSTART_RUN_NAME,
        )
        is not None
    )
    return state


# ---------- High-Level Install-Workflow -------------------------------------


def perform_install(
    *,
    backend: RegistryBackend,
    create_profile: bool,
    profile_name: str,
    with_hotkeys: bool,
    profile_creator: Callable[[str], None] | None = None,
) -> InstallResult:
    """Führe den vollständigen Install-Workflow durch (Profil + Registry).

    ``profile_creator`` ist ein Callable ``(name: str) -> None``, das das
    Default-Profil im Simple-Mode anlegt. Production: das CLI übergibt
    ``manager.open_or_create_simple``. Test: stubbed.

    Diese Funktion ist Plattform-agnostisch — sie ruft nur den Backend
    an. Die CLI entscheidet, ob :class:`WinRegistryBackend` oder ein
    macOS-Pendant (folgt in einem späteren Schritt) verwendet wird.
    """
    notes: list[str] = []
    created = False
    profile_error: str | None = None
    if create_profile and profile_creator is not None:
        try:
            profile_creator(profile_name)
            created = True
        except FileExistsError:
            notes.append(f"Profil '{profile_name}' existierte bereits — nicht überschrieben.")
        except Exception as exc:  # pragma: no cover - vorsichtig
            # Hartes Failure-Signal — User hat das Profil angefragt, wir
            # konnten es nicht liefern. Wird in CLI/Tests inspiziert.
            profile_error = str(exc)

    registered, skipped = install_context_menu(backend)

    autostart = False
    if with_hotkeys:
        try:
            install_autostart(backend, profile=profile_name)
            autostart = True
        except OSError as exc:
            notes.append(f"Autostart konnte nicht registriert werden: {exc}")

    return InstallResult(
        extensions_registered=registered,
        extensions_skipped=skipped,
        autostart_registered=autostart,
        profile_created=created,
        profile_name=profile_name,
        notes=tuple(notes),
        profile_error=profile_error,
    )


def perform_uninstall(*, backend: RegistryBackend) -> tuple[tuple[str, ...], bool]:
    """Entferne sämtliche Registry-Einträge (Context-Menu + Autostart).
    Profile bleiben unberührt — die löscht nur ``profiles remove``."""
    removed_ext = uninstall_context_menu(backend)
    removed_autostart = uninstall_autostart(backend)
    return removed_ext, removed_autostart


def default_backend() -> RegistryBackend:
    """Wähle den Production-Backend abhängig vom Betriebssystem.

    Aktuell: Windows → WinRegistryBackend. macOS/Linux → RuntimeError
    (Context-Menu-Integration ist Phase-B-Windows-only; macOS-Services
    + Linux-Desktop-Entries kommen in einem Folge-PR).
    """
    if sys.platform != "win32":
        raise RuntimeError(
            "Pseudokrat-Install ist aktuell nur unter Windows verfügbar. "
            "Auf macOS/Linux kannst du Pseudokrat direkt per CLI nutzen "
            "(pseudokrat anonymize ...)."
        )
    return WinRegistryBackend()


# ---------- Pfad-Helpers (für CLI-Reports) ----------------------------------


def expected_pseudokrat_exe() -> Path | None:
    """Wo wir ``pseudokrat.exe`` vermuten — für „nicht im PATH"-
    Warnungen im CLI."""
    found = shutil.which("pseudokrat")
    if found is not None:
        return Path(found)
    # Heuristik: gleiches Verzeichnis wie python.exe (venv-Scripts).
    py_dir = Path(sys.executable).parent
    candidate = py_dir / "pseudokrat.exe"
    return candidate if candidate.exists() else None
