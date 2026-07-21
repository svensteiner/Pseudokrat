from __future__ import annotations

from pathlib import Path

from tools.release_gate import project_version, validate_release

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_packaging_metadata_is_consistent() -> None:
    assert validate_release(REPO_ROOT) == []


def test_release_tag_must_match_project_version() -> None:
    version = project_version(REPO_ROOT)
    assert validate_release(REPO_ROOT, tag=f"v{version}") == []
    errors = validate_release(REPO_ROOT, tag="v999.0.0")
    assert any("passt nicht" in error for error in errors)


def test_installer_does_not_register_unsupported_global_file_command() -> None:
    installer = (REPO_ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "Software\\Classes\\*\\shell" not in installer
    assert "--file" not in installer


def test_start_scripts_propagate_failures() -> None:
    for relative in ("START.bat", "packaging/gumroad/START.bat", "Anonymisierung starten.bat"):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "exit /b %RC%" in source
