"""Pseudokrat-Desktop-GUI (Phase 2).

Minimaler PySide6-Shell mit Live-Tab und Profil-Auswahl. Wird über
``python -m pseudokrat.gui`` oder den Entry-Point ``pseudokrat-gui``
gestartet (siehe pyproject.toml).

Der ``main_window``-Submodule importiert PySide6 und wird daher lazy
geladen — so kann ``pseudokrat.gui.controller`` (UI-frei) auch in
Umgebungen ohne PySide6 importiert werden (z. B. headless CI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pseudokrat.gui.main_window import MainWindow, build_application, run
    from pseudokrat.gui.wizard import FirstStartWizard, first_start_required

__all__ = [
    "FirstStartWizard",
    "MainWindow",
    "build_application",
    "first_start_required",
    "run",
]


_WIZARD_EXPORTS = {"FirstStartWizard", "first_start_required"}


def __getattr__(name: str) -> Any:
    if name in _WIZARD_EXPORTS:
        from pseudokrat.gui import wizard

        return getattr(wizard, name)
    if name in __all__:
        from pseudokrat.gui import main_window

        return getattr(main_window, name)
    raise AttributeError(f"module 'pseudokrat.gui' has no attribute {name!r}")
