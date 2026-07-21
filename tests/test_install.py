"""Tests für die Windows-Integration (`pseudokrat install`/`uninstall`).

Verwendet :class:`InMemoryRegistryBackend`, damit die Suite auch ohne
echte Windows-Registry läuft (CI auf Linux/macOS).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.install import (
    AUTOSTART_RUN_NAME,
    CONTEXT_MENU_KEY,
    CONTEXT_MENU_LABEL,
    SUPPORTED_EXTENSIONS,
    InMemoryRegistryBackend,
    InstallResult,
    _context_menu_subkey,
    check_install_state,
    install_autostart,
    install_context_menu,
    perform_install,
    perform_uninstall,
    resolve_hotkey_daemon_command,
    resolve_pseudokrat_command,
    uninstall_autostart,
    uninstall_context_menu,
)

# --- InMemoryRegistryBackend Basis ------------------------------------------


def test_in_memory_backend_set_and_get() -> None:
    backend = InMemoryRegistryBackend()
    backend.set_string("HKCU", "Software\\Foo", "Bar", "value1")
    assert backend.get_string("HKCU", "Software\\Foo", "Bar") == "value1"


def test_in_memory_backend_get_missing_returns_none() -> None:
    backend = InMemoryRegistryBackend()
    assert backend.get_string("HKCU", "Software\\Foo", "Bar") is None


def test_in_memory_backend_delete_value_idempotent() -> None:
    backend = InMemoryRegistryBackend()
    # Idempotent: kein Fehler bei nicht-existierendem Wert.
    backend.delete_value("HKCU", "Software\\Foo", "Bar")
    backend.set_string("HKCU", "Software\\Foo", "Bar", "value1")
    backend.delete_value("HKCU", "Software\\Foo", "Bar")
    assert backend.get_string("HKCU", "Software\\Foo", "Bar") is None


def test_in_memory_backend_delete_tree_removes_subkeys() -> None:
    backend = InMemoryRegistryBackend()
    backend.set_string("HKCU", "Software\\Foo", "A", "1")
    backend.set_string("HKCU", "Software\\Foo\\Bar", "B", "2")
    backend.set_string("HKCU", "Software\\Foo\\Bar\\Baz", "C", "3")
    backend.set_string("HKCU", "Software\\Other", "D", "4")

    backend.delete_tree("HKCU", "Software\\Foo")

    assert backend.get_string("HKCU", "Software\\Foo", "A") is None
    assert backend.get_string("HKCU", "Software\\Foo\\Bar", "B") is None
    assert backend.get_string("HKCU", "Software\\Foo\\Bar\\Baz", "C") is None
    # Andere Bäume bleiben unberührt
    assert backend.get_string("HKCU", "Software\\Other", "D") == "4"


def test_in_memory_backend_subkey_exists() -> None:
    backend = InMemoryRegistryBackend()
    assert not backend.subkey_exists("HKCU", "Software\\Foo")
    backend.set_string("HKCU", "Software\\Foo", "A", "1")
    assert backend.subkey_exists("HKCU", "Software\\Foo")


def test_in_memory_backend_rejects_unknown_hive() -> None:
    backend = InMemoryRegistryBackend()
    with pytest.raises(ValueError):
        backend.set_string("HKBLARG", "x", "y", "z")


# --- Context-Menu-Installation ----------------------------------------------


def test_install_context_menu_writes_all_extensions() -> None:
    backend = InMemoryRegistryBackend()
    registered, skipped = install_context_menu(backend, command_template='"foo.exe" "%1"')
    assert set(registered) == set(SUPPORTED_EXTENSIONS)
    assert skipped == ()
    for ext in SUPPORTED_EXTENSIONS:
        base = _context_menu_subkey(ext)
        assert backend.get_string("HKCU", base, "") == CONTEXT_MENU_LABEL
        assert backend.get_string("HKCU", f"{base}\\command", "") == '"foo.exe" "%1"'


def test_install_context_menu_custom_extension_subset() -> None:
    backend = InMemoryRegistryBackend()
    registered, skipped = install_context_menu(
        backend, extensions=(".pdf", ".csv"), command_template='"x" "%1"'
    )
    assert set(registered) == {".pdf", ".csv"}
    assert skipped == ()
    assert not backend.subkey_exists("HKCU", _context_menu_subkey(".docx"))


def test_uninstall_context_menu_removes_only_our_keys() -> None:
    backend = InMemoryRegistryBackend()
    install_context_menu(backend, command_template='"x" "%1"')
    # Fremde Nachbar-Subkeys
    backend.set_string(
        "HKCU",
        "Software\\Classes\\SystemFileAssociations\\.pdf\\shell\\AdobeReader",
        "",
        "Open with Adobe",
    )
    removed = uninstall_context_menu(backend)
    assert set(removed) == set(SUPPORTED_EXTENSIONS)
    for ext in SUPPORTED_EXTENSIONS:
        assert not backend.subkey_exists("HKCU", _context_menu_subkey(ext))
    # Fremder Subkey bleibt erhalten
    assert (
        backend.get_string(
            "HKCU",
            "Software\\Classes\\SystemFileAssociations\\.pdf\\shell\\AdobeReader",
            "",
        )
        == "Open with Adobe"
    )


def test_uninstall_context_menu_idempotent() -> None:
    backend = InMemoryRegistryBackend()
    # Nichts installiert — sollte keinen Fehler werfen
    removed = uninstall_context_menu(backend)
    assert removed == ()


# --- Autostart --------------------------------------------------------------


def test_install_autostart_writes_run_entry() -> None:
    backend = InMemoryRegistryBackend()
    install_autostart(
        backend, profile="alice", command_template='"x" hotkey-daemon --profile "alice"'
    )
    value = backend.get_string(
        "HKCU",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        AUTOSTART_RUN_NAME,
    )
    assert value == '"x" hotkey-daemon --profile "alice"'


def test_install_autostart_overwrites_existing() -> None:
    backend = InMemoryRegistryBackend()
    install_autostart(backend, profile="alice", command_template="cmd1")
    install_autostart(backend, profile="alice", command_template="cmd2")
    value = backend.get_string(
        "HKCU",
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        AUTOSTART_RUN_NAME,
    )
    assert value == "cmd2"


def test_uninstall_autostart_returns_true_when_removed() -> None:
    backend = InMemoryRegistryBackend()
    install_autostart(backend, profile="alice", command_template="cmd")
    assert uninstall_autostart(backend) is True
    assert (
        backend.get_string(
            "HKCU",
            "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            AUTOSTART_RUN_NAME,
        )
        is None
    )


def test_uninstall_autostart_returns_false_when_missing() -> None:
    backend = InMemoryRegistryBackend()
    assert uninstall_autostart(backend) is False


# --- check_install_state ----------------------------------------------------


def test_check_install_state_all_false_when_clean() -> None:
    backend = InMemoryRegistryBackend()
    state = check_install_state(backend)
    for ext in SUPPORTED_EXTENSIONS:
        assert state[ext] is False
    assert state["autostart"] is False


def test_check_install_state_reflects_install() -> None:
    backend = InMemoryRegistryBackend()
    install_context_menu(backend, command_template="cmd")
    install_autostart(backend, profile="alice", command_template="hk")
    state = check_install_state(backend)
    for ext in SUPPORTED_EXTENSIONS:
        assert state[ext] is True
    assert state["autostart"] is True


# --- perform_install / perform_uninstall ------------------------------------


def test_perform_install_full_workflow_with_hotkeys() -> None:
    backend = InMemoryRegistryBackend()
    created_profiles: list[str] = []

    def creator(name: str) -> None:
        created_profiles.append(name)

    result = perform_install(
        backend=backend,
        create_profile=True,
        profile_name="Mein Konto",
        with_hotkeys=True,
        profile_creator=creator,
    )
    assert isinstance(result, InstallResult)
    assert result.profile_created is True
    assert result.profile_name == "Mein Konto"
    assert created_profiles == ["Mein Konto"]
    assert set(result.extensions_registered) == set(SUPPORTED_EXTENSIONS)
    assert result.extensions_skipped == ()
    assert result.autostart_registered is True


def test_perform_install_no_profile_no_hotkeys() -> None:
    backend = InMemoryRegistryBackend()
    result = perform_install(
        backend=backend,
        create_profile=False,
        profile_name="Mein Konto",
        with_hotkeys=False,
        profile_creator=None,
    )
    assert result.profile_created is False
    assert result.autostart_registered is False
    # Context-Menu wird trotzdem registriert
    assert set(result.extensions_registered) == set(SUPPORTED_EXTENSIONS)


def test_perform_install_existing_profile_noted() -> None:
    backend = InMemoryRegistryBackend()

    def creator(name: str) -> None:
        raise FileExistsError(f"{name} existiert")

    result = perform_install(
        backend=backend,
        create_profile=True,
        profile_name="Mein Konto",
        with_hotkeys=False,
        profile_creator=creator,
    )
    assert result.profile_created is False
    assert any("existierte bereits" in note for note in result.notes)
    # Aber Context-Menu wurde dennoch registriert
    assert len(result.extensions_registered) == len(SUPPORTED_EXTENSIONS)


def test_cli_install_returns_nonzero_when_profile_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-End: CLI muss bei Profil-Failure Exit != 0 zurückgeben,
    sonst werten Skripte/CI Install fälschlich als success."""
    import pseudokrat.cli as cli_mod
    import pseudokrat.install as install_mod

    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))

    def fake_perform_install(**kwargs):  # type: ignore[no-untyped-def]
        return InstallResult(
            extensions_registered=SUPPORTED_EXTENSIONS,
            extensions_skipped=(),
            autostart_registered=False,
            profile_created=False,
            profile_name=kwargs["profile_name"],
            notes=(),
            profile_error="Simple-Mode benötigt die Keyring-Bibliothek.",
        )

    # cli importiert ``perform_install``/``default_backend`` lokal aus
    # ``pseudokrat.install`` — also dort patchen.
    monkeypatch.setattr(install_mod, "perform_install", fake_perform_install)
    monkeypatch.setattr(install_mod, "default_backend", InMemoryRegistryBackend)

    rc = cli_mod.main(["install", "--no-hotkeys"])
    assert rc == 16
    stderr = capsys.readouterr().err
    assert "KONNTE NICHT angelegt" in stderr


def test_perform_install_profile_failure_is_critical() -> None:
    """Iter-14: Wenn das angefragte Profil nicht angelegt werden kann,
    ist das ein hartes Failure — nicht eine ℹ-Note unten am Output.

    Treiber: `pseudokrat install` ohne `[simple-mode]`-Extra scheiterte
    leise mit Exit 0; Doctor schlug danach Alarm und der Pilot-Tester
    verstand nicht, warum.
    """
    backend = InMemoryRegistryBackend()

    def creator(name: str) -> None:
        raise RuntimeError(
            "Simple-Mode benötigt die Keyring-Bibliothek. Installiere mit:\n"
            "  pip install pseudokrat[simple-mode]"
        )

    result = perform_install(
        backend=backend,
        create_profile=True,
        profile_name="Mein Konto",
        with_hotkeys=False,
        profile_creator=creator,
    )
    assert result.profile_created is False
    assert result.profile_error is not None
    assert "Keyring-Bibliothek" in result.profile_error
    assert result.has_critical_failure is True
    # Note-Slot bleibt sauber — wir tarnen den Fehler nicht als ℹ-Note.
    assert not any("konnte nicht angelegt" in note for note in result.notes)
    # Context-Menu wird trotzdem registriert (best-effort).
    assert set(result.extensions_registered) == set(SUPPORTED_EXTENSIONS)


def test_perform_install_successful_profile_has_no_error() -> None:
    backend = InMemoryRegistryBackend()
    result = perform_install(
        backend=backend,
        create_profile=True,
        profile_name="OK",
        with_hotkeys=False,
        profile_creator=lambda _name: None,
    )
    assert result.profile_created is True
    assert result.profile_error is None
    assert result.has_critical_failure is False


def test_perform_uninstall_removes_everything() -> None:
    backend = InMemoryRegistryBackend()
    install_context_menu(backend, command_template="cmd")
    install_autostart(backend, profile="alice", command_template="hk")

    removed_ext, removed_autostart = perform_uninstall(backend=backend)
    assert set(removed_ext) == set(SUPPORTED_EXTENSIONS)
    assert removed_autostart is True

    state = check_install_state(backend)
    for ext in SUPPORTED_EXTENSIONS:
        assert state[ext] is False
    assert state["autostart"] is False


# --- Command-Resolution -----------------------------------------------------


def test_resolve_pseudokrat_command_contains_placeholder() -> None:
    cmd = resolve_pseudokrat_command()
    assert "%1" in cmd
    assert "anonymize" in cmd
    assert '--profile "Mein Konto"' in cmd
    assert "--no-ml" in cmd
    # Quoting für Pfade mit Spaces
    assert cmd.count('"') >= 2


def test_resolve_pseudokrat_command_uses_frozen_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pseudokrat.install.sys.frozen", True, raising=False)
    monkeypatch.setattr("pseudokrat.install.sys.executable", r"C:\Program Files\Pseudokrat.exe")
    monkeypatch.setattr("pseudokrat.install.shutil.which", lambda _name: None)

    cmd = resolve_pseudokrat_command("Kanzlei")

    assert cmd.startswith(r'"C:\Program Files\Pseudokrat.exe" anonymize')
    assert " -m pseudokrat " not in cmd
    assert '--profile "Kanzlei"' in cmd


def test_resolve_commands_reject_command_line_injection() -> None:
    with pytest.raises(ValueError):
        resolve_pseudokrat_command('Kanzlei" & calc.exe & "')
    with pytest.raises(ValueError):
        resolve_hotkey_daemon_command("Kanzlei\r\nBad")


def test_perform_install_registers_selected_profile() -> None:
    backend = InMemoryRegistryBackend()

    perform_install(
        backend=backend,
        create_profile=False,
        profile_name="Kanzlei",
        with_hotkeys=False,
    )

    command = backend.get_string(
        "HKCU",
        f"{_context_menu_subkey('.pdf')}\\command",
        "",
    )
    assert command is not None
    assert '--profile "Kanzlei"' in command
    assert "--no-ml" in command


def test_resolve_hotkey_daemon_command_includes_profile() -> None:
    cmd = resolve_hotkey_daemon_command("Mein Konto")
    assert "hotkey-daemon" in cmd
    assert "Mein Konto" in cmd


def test_resolve_hotkey_command_uses_frozen_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pseudokrat.install.sys.frozen", True, raising=False)
    monkeypatch.setattr("pseudokrat.install.sys.executable", r"C:\Pseudokrat.exe")
    monkeypatch.setattr("pseudokrat.install.shutil.which", lambda _name: None)

    cmd = resolve_hotkey_daemon_command("Mein Konto")

    assert cmd.startswith(r'"C:\Pseudokrat.exe" hotkey-daemon')
    assert " -m pseudokrat " not in cmd


def test_context_menu_subkey_format() -> None:
    sub = _context_menu_subkey(".pdf")
    assert sub.endswith(f"\\{CONTEXT_MENU_KEY}")
    assert ".pdf" in sub
    assert "SystemFileAssociations" in sub
