"""Headless-Tests für den Erst-Start-Wizard (§9 Megaprompt).

Der Wizard wird ohne ``exec()`` getestet — Tests konstruieren den
Wizard, setzen die Felder direkt auf den Page-Widgets und rufen
:meth:`FirstStartWizard.try_create_profile` auf bzw. simulieren
einen Page-Wechsel über ``next()``. Eine echte Modale-Schleife
ist nicht nötig.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402

from pseudokrat.gui.controller import GuiController  # noqa: E402
from pseudokrat.gui.main_window import build_application  # noqa: E402
from pseudokrat.gui.wizard import (  # noqa: E402
    MIN_PASSWORD_LENGTH,
    FirstStartWizard,
    first_start_required,
)


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or build_application(["pseudokrat-tests"])


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


@pytest.fixture
def controller() -> GuiController:
    return GuiController()


@pytest.fixture
def wizard(
    qt_app: QApplication,
    controller: GuiController,
    monkeypatch: pytest.MonkeyPatch,
) -> FirstStartWizard:
    """Wizard ohne UI-Warnings — Fehlermeldungen werden in `warnings` gesammelt."""
    captured: list[str] = []
    monkeypatch.setattr(
        FirstStartWizard,
        "_warn",
        lambda self, msg: captured.append(msg),  # type: ignore[misc]
    )
    w = FirstStartWizard(controller)
    w._captured_warnings = captured  # type: ignore[attr-defined]
    return w


def test_first_start_required_true_when_no_profiles(controller: GuiController) -> None:
    assert first_start_required(controller) is True


def test_first_start_required_false_after_profile_created(controller: GuiController) -> None:
    controller.create_profile("Allgemein", "supergeheim")
    assert first_start_required(controller) is False


def test_wizard_has_four_pages(wizard: FirstStartWizard) -> None:
    assert wizard.pageIds() == [0, 1, 2, 3]
    assert wizard.welcome_page.title() == "Willkommen bei Pseudokrat"
    assert wizard.profile_page.title() == "Profil anlegen"
    assert wizard.model_page.title().startswith("ML-Modell")
    assert wizard.summary_page.title() == "Profil angelegt"


def test_model_page_reports_missing_cache(wizard: FirstStartWizard) -> None:
    wizard.model_page.initializePage()
    text = wizard.model_page.info_label.text()
    assert "Cache-Verzeichnis" in text
    assert wizard.model_page.download_checkbox.isEnabled()


def test_model_page_does_not_block_when_unchecked(wizard: FirstStartWizard) -> None:
    wizard.model_page.initializePage()
    wizard.model_page.download_checkbox.setChecked(False)
    assert wizard.model_page.validatePage() is True


def test_buttons_are_localized_to_german(wizard: FirstStartWizard) -> None:
    from PySide6.QtWidgets import QWizard

    assert wizard.buttonText(QWizard.WizardButton.NextButton) == "Weiter"
    assert wizard.buttonText(QWizard.WizardButton.BackButton) == "Zurück"
    assert wizard.buttonText(QWizard.WizardButton.FinishButton) == "Fertigstellen"
    assert wizard.buttonText(QWizard.WizardButton.CancelButton) == "Abbrechen"


def test_try_create_profile_rejects_short_password(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("Mandant Hofer")
    wizard.profile_page.password_input.setText("kurz")
    wizard.profile_page.password_confirm_input.setText("kurz")
    assert wizard.try_create_profile() is False
    captured = wizard._captured_warnings  # type: ignore[attr-defined]
    assert any(str(MIN_PASSWORD_LENGTH) in m for m in captured)
    assert wizard.created_profile is None


def test_try_create_profile_rejects_password_mismatch(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("Mandant Hofer")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim-tippfehler")
    assert wizard.try_create_profile() is False
    captured = wizard._captured_warnings  # type: ignore[attr-defined]
    assert any("stimmen nicht überein" in m for m in captured)


def test_try_create_profile_rejects_empty_name(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("   ")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    assert wizard.try_create_profile() is False
    captured = wizard._captured_warnings  # type: ignore[attr-defined]
    assert any("Profilnamen" in m for m in captured)


def test_try_create_profile_rejects_invalid_mandanten_regex(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("Mandant Hofer")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    wizard.profile_page.mandanten_pattern_input.setText(r"M-[")  # offene Klasse
    assert wizard.try_create_profile() is False
    captured = wizard._captured_warnings  # type: ignore[attr-defined]
    assert any("Regex" in m or "gültig" in m for m in captured)
    # Profil darf NICHT angelegt worden sein:
    assert wizard.controller.list_profile_summaries() == []


def test_try_create_profile_happy_path_persists_profile(
    wizard: FirstStartWizard,
    controller: GuiController,
) -> None:
    wizard.profile_page.profile_name_input.setText("Mandant Hofer")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    assert wizard.try_create_profile() is True
    assert wizard.created_profile is not None
    assert wizard.created_profile.name == "Mandant Hofer"
    summaries = controller.list_profile_summaries()
    assert [s.name for s in summaries] == ["Mandant Hofer"]


def test_try_create_profile_with_mandanten_pattern_is_persisted(
    wizard: FirstStartWizard,
    controller: GuiController,
) -> None:
    wizard.profile_page.profile_name_input.setText("Kanzlei Müller")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    wizard.profile_page.mandanten_pattern_input.setText(r"M-\d{5}")
    assert wizard.try_create_profile() is True
    assert wizard.mandanten_pattern_used == r"M-\d{5}"

    # Profil muss das Mandanten-Pattern erkennen, wenn es regulär geöffnet wird.
    controller.open_profile("Kanzlei Müller", "supergeheim")
    try:
        text, counts = controller.anonymize("Mandant M-12345 ist neu.")
        assert "<MANDANT_NR_001>" in text
        assert counts.get("MANDANT_NR") == 1
    finally:
        controller.close()


def test_try_create_profile_rejects_duplicate(
    wizard: FirstStartWizard,
    controller: GuiController,
) -> None:
    controller.create_profile("Allgemein", "supergeheim")
    wizard.profile_page.profile_name_input.setText("Allgemein")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    assert wizard.try_create_profile() is False
    captured = wizard._captured_warnings  # type: ignore[attr-defined]
    assert any("existiert bereits" in m for m in captured)


def test_summary_page_renders_after_creation(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("Mandant Hofer")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    assert wizard.try_create_profile() is True
    wizard.summary_page.initializePage()
    text = wizard.summary_page.summary_label.text()
    assert "Mandant Hofer" in text
    assert "Fertigstellen" in text


def test_summary_page_renders_pattern_when_set(wizard: FirstStartWizard) -> None:
    wizard.profile_page.profile_name_input.setText("Kanzlei Schmidt")
    wizard.profile_page.password_input.setText("supergeheim")
    wizard.profile_page.password_confirm_input.setText("supergeheim")
    wizard.profile_page.mandanten_pattern_input.setText(r"MND-\d{4}")
    assert wizard.try_create_profile() is True
    wizard.summary_page.initializePage()
    text = wizard.summary_page.summary_label.text()
    assert r"MND-\d{4}" in text


def test_summary_page_defensive_fallback_when_no_profile(wizard: FirstStartWizard) -> None:
    # Direkter Aufruf von initializePage ohne vorherige Anlage:
    wizard.summary_page.initializePage()
    assert "Kein Profil" in wizard.summary_page.summary_label.text()
