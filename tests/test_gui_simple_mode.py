"""Tests für den Simple-Mode-GUI-Pfad (Phase C).

Validiert, dass das Hauptfenster bei genau einem Simple-Mode-Profil
den Profil-Selector + Profile-Tab versteckt, das Profil automatisch
öffnet, und Close-Events in die Tray minimieren statt zu beenden.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

# Qt-Plattform offscreen — vor PySide6-Import setzen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pseudokrat.gui.controller import GuiController  # noqa: E402
from pseudokrat.gui.main_window import MainWindow, build_application  # noqa: E402
from pseudokrat.store.key_protector import InMemoryKeyringBackend  # noqa: E402
from pseudokrat.store.profile import ProfileManager  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or build_application(["pseudokrat-simple-tests"])


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def _create_simple_profile(
    name: str = "Mein Konto",
) -> tuple[ProfileManager, InMemoryKeyringBackend]:
    """Erzeugt ein Simple-Mode-Profil mit einem In-Memory-Keyring-Backend."""
    backend = InMemoryKeyringBackend()
    manager = ProfileManager()
    store, _audit = manager.open_or_create_simple(name, backend=backend)
    store.close()
    return manager, backend


# --- detect_simple_default --------------------------------------------------


def test_detect_simple_default_returns_name_for_single_simple_profile() -> None:
    manager, _ = _create_simple_profile("Mein Konto")
    assert manager.detect_simple_default() == "Mein Konto"


def test_detect_simple_default_returns_none_when_no_profiles() -> None:
    manager = ProfileManager()
    assert manager.detect_simple_default() is None


def test_detect_simple_default_returns_none_when_password_profile() -> None:
    manager = ProfileManager()
    store, _ = manager.open_or_create("classic", "geheim123")
    store.close()
    assert manager.detect_simple_default() is None


def test_detect_simple_default_returns_none_when_multiple_profiles() -> None:
    manager, backend = _create_simple_profile("A")
    store, _ = manager.open_or_create_simple("B", backend=backend)
    store.close()
    assert manager.detect_simple_default() is None


# --- MainWindow Simple-Mode -------------------------------------------------


def test_main_window_hides_profile_row_in_simple_mode(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, backend = _create_simple_profile("Mein Konto")
    monkeypatch.setattr(
        "pseudokrat.store.key_protector.SystemKeyringBackend",
        lambda: backend,
    )
    win = MainWindow()
    try:
        # Profil-Auswahl-Zeile ist explizit versteckt (isHidden statt
        # isVisible, weil unter offscreen-Plattform der MainWindow nicht
        # auto-visible ist).
        assert win._profile_row_widget.isHidden()
        # Tabs sind nur Live + Datei, kein Profile-Tab.
        tab_titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert tab_titles == ["Live", "Datei"]
        # Simple-Mode-Flag ist gesetzt.
        assert win._simple_mode is True
        assert win._simple_default == "Mein Konto"
    finally:
        win._simple_mode = False  # Bypass Tray-Minimize beim Close
        win.close()


def test_main_window_falls_back_to_full_mode_when_no_simple_profile(
    qt_app: QApplication,
) -> None:
    win = MainWindow()
    try:
        # Profil-Row nicht explizit verborgen (isHidden=False), Profile-Tab vorhanden.
        assert not win._profile_row_widget.isHidden()
        tab_titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert "Profile" in tab_titles
        assert win._simple_mode is False
    finally:
        win.close()


def test_main_window_force_full_mode_overrides_simple_default(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`force_full_mode=True` zwingt die Power-User-UI auch bei
    vorhandenem Simple-Profil — gebraucht für Tests und für einen
    künftigen Menü-Eintrag „Erweitert"."""
    _, backend = _create_simple_profile("Mein Konto")
    monkeypatch.setattr(
        "pseudokrat.store.key_protector.SystemKeyringBackend",
        lambda: backend,
    )
    win = MainWindow(force_full_mode=True)
    try:
        assert win._simple_mode is False
        assert not win._profile_row_widget.isHidden()
        tab_titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        assert "Profile" in tab_titles
    finally:
        win.close()


def test_main_window_auto_opens_simple_profile_session(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, backend = _create_simple_profile("Mein Konto")
    monkeypatch.setattr(
        "pseudokrat.store.key_protector.SystemKeyringBackend",
        lambda: backend,
    )
    win = MainWindow()
    try:
        # Nach __init__ ist eine Session aktiv.
        assert win._controller.session is not None
        assert win._controller.session.profile_name == "Mein Konto"
        # Action-Buttons sind aktiv.
        assert win.anonymize_button.isEnabled()
        assert win.deanonymize_button.isEnabled()
    finally:
        win._simple_mode = False
        win.close()


def test_main_window_close_minimizes_to_tray_in_simple_mode(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, backend = _create_simple_profile("Mein Konto")
    monkeypatch.setattr(
        "pseudokrat.store.key_protector.SystemKeyringBackend",
        lambda: backend,
    )
    win = MainWindow()
    try:
        # Tray-Icon sichtbar mocken, damit der Minimize-Pfad greift.
        with (
            patch.object(win.tray_icon, "isVisible", return_value=True),
            patch.object(win.tray_icon, "showMessage") as mock_msg,
        ):
            event = QCloseEvent()
            win.show()
            win.closeEvent(event)
            assert not event.isAccepted()
            assert not win.isVisible()
            mock_msg.assert_called_once()
    finally:
        win._simple_mode = False
        win.close()


def test_main_window_close_quits_normally_in_full_mode(qt_app: QApplication) -> None:
    win = MainWindow()
    try:
        event = QCloseEvent()
        win.closeEvent(event)
        # Im Full-Mode wird der Close-Event akzeptiert (Default-Verhalten).
        assert event.isAccepted()
    finally:
        win.close()


# --- GuiController.open_simple_profile --------------------------------------


def test_open_simple_profile_activates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _, backend = _create_simple_profile("Mein Konto")
    monkeypatch.setattr(
        "pseudokrat.store.key_protector.SystemKeyringBackend",
        lambda: backend,
    )
    controller = GuiController()
    controller.open_simple_profile("Mein Konto")
    assert controller.session is not None
    assert controller.session.profile_name == "Mein Konto"
    controller.close()


def test_open_simple_profile_rejects_empty_name() -> None:
    controller = GuiController()
    from pseudokrat.gui.controller import GuiError

    with pytest.raises(GuiError):
        controller.open_simple_profile("")
