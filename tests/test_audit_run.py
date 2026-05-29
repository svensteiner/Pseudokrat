"""Tests für die PRL-Audit-Phase (``tools/audit_run.py``).

Strategie: Subprocess-Aufrufe werden gemockt, damit Tests in
Millisekunden laufen statt Sekunden. Die Trust-Boundary-Coverage-
Heuristik testen wir direkt — sie operiert auf Dateien, kein
Subprocess.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools import audit_run


def _fake_run_factory(rc: int, stdout: str = "", stderr: str = ""):
    def fake(cmd, **kwargs):
        return (rc, stdout, stderr, 0.01)

    return fake


# --- Einzel-Checks ---------------------------------------------------------


def test_check_ruff_pass() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(0, "All checks passed!")):
        r = audit_run.check_ruff()
    assert r.status == "pass"
    assert r.returncode == 0


def test_check_ruff_fail() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(1, "Found 1 error.")):
        r = audit_run.check_ruff()
    assert r.status == "fail"


def test_check_mypy_pass() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(0, "Success: no issues found")):
        r = audit_run.check_mypy()
    assert r.status == "pass"


def test_check_pytest_pass_skip_slow() -> None:
    captured = {}

    def fake(cmd, **kwargs):
        captured["cmd"] = cmd
        return (0, "100 passed", "", 1.0)

    with patch.object(audit_run, "_run", fake):
        r = audit_run.check_pytest(skip_slow=True)
    assert r.status == "pass"
    assert "-m" in captured["cmd"]
    assert "not slow" in captured["cmd"]


def test_check_pytest_include_slow() -> None:
    captured = {}

    def fake(cmd, **kwargs):
        captured["cmd"] = cmd
        return (0, "all passed", "", 1.0)

    with patch.object(audit_run, "_run", fake):
        audit_run.check_pytest(skip_slow=False)
    # Bei include-slow darf "not slow" NICHT in cmd stehen.
    assert "not slow" not in captured["cmd"]


def test_check_bandit_pass() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(0)):
        r = audit_run.check_bandit()
    assert r.status == "pass"


def test_check_bandit_fail_means_findings() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(1, "Total findings: 3")):
        r = audit_run.check_bandit()
    assert r.status == "fail"


def test_check_pip_audit_skipped_when_missing() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(1, "", "No module named pip_audit")):
        r = audit_run.check_pip_audit()
    assert r.status == "skipped"
    assert "pip-audit" in r.stderr_tail


def test_check_pip_audit_pass() -> None:
    with patch.object(audit_run, "_run", _fake_run_factory(0)):
        r = audit_run.check_pip_audit()
    assert r.status == "pass"


# --- Trust-Boundary-Heuristik ----------------------------------------------


def test_extract_boundaries_parses_self_audit_headings(tmp_path: Path) -> None:
    self_audit = tmp_path / "SELF_AUDIT.md"
    self_audit.write_text(
        "# Self Audit\n\n"
        "### S1 — Datei-Eingabe-Vektor\n\n"
        "Inhalt …\n\n"
        "### S2 — CLI-Validierung\n\n"
        "### S7 — Windows-Registry-Integration (D-040)\n",
        encoding="utf-8",
    )
    boundaries = audit_run._extract_boundaries(self_audit)
    assert ("S1", "Datei-Eingabe-Vektor") in boundaries
    assert ("S2", "CLI-Validierung") in boundaries
    # Auch parenthesized trailing parts werden mitgenommen.
    assert any(b[0] == "S7" for b in boundaries)


def test_extract_boundaries_returns_empty_when_self_audit_missing(tmp_path: Path) -> None:
    assert audit_run._extract_boundaries(tmp_path / "nada.md") == []


def test_trust_boundary_coverage_pass_when_all_referenced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path
    (repo / "SELF_AUDIT.md").write_text(
        "### S1 — Beispielboundary\n", encoding="utf-8"
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text(
        '"""Test referenziert S1 ausführlich."""\n', encoding="utf-8"
    )
    monkeypatch.setattr(audit_run, "REPO_ROOT", repo)
    r = audit_run.check_trust_boundary_coverage()
    assert r.status == "pass"
    assert r.extra["per_boundary"]["S1"]["covered"] is True


def test_trust_boundary_stem_matches_inflected_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Title-Stem (erste 5 Zeichen) matcht morphologische Varianten:
    'Permutation' → 'permu' matcht Test-Dateien mit 'permute'."""
    repo = tmp_path
    (repo / "SELF_AUDIT.md").write_text(
        "### S5 — DP-Permutation (SECURITY_MODEL)\n", encoding="utf-8"
    )
    (repo / "tests").mkdir()
    (repo / "tests" / "test_dp_numeric_permute.py").write_text(
        '"""Tests fuer die rangbewahrende Beträge-Permute-Funktion."""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(audit_run, "REPO_ROOT", repo)
    r = audit_run.check_trust_boundary_coverage()
    assert r.status == "pass"
    assert r.extra["per_boundary"]["S5"]["covered"] is True


def test_title_keywords_handles_hyphenated_title() -> None:
    stems = audit_run._title_keywords("DP-Permutation (SECURITY_MODEL §8)")
    # Bindestrich gesplittet, "DP" zu kurz, "SECURITY" + "MODEL" als Stopwords.
    assert "permu" in stems


def test_title_keywords_filters_stopwords() -> None:
    stems = audit_run._title_keywords("Der Eingabe-Vektor und das Modell")
    # "Der", "und", "das" sind Stopwords. "Modell" ist drin.
    assert "der" not in stems
    assert "und" not in stems
    assert "modell"[:5] in stems


def test_trust_boundary_coverage_fail_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path
    (repo / "SELF_AUDIT.md").write_text(
        "### S42 — Verwaiste Boundary mit einzigartigem Keyword Zwiebelfisch\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    # Testdatei darf weder den S-Code noch das Keyword (case-insensitive)
    # enthalten — sonst meldet die Heuristik fälschlich "covered".
    (repo / "tests" / "test_x.py").write_text(
        '"""Inhaltlich völlig anderer Test ohne Bezug."""\n', encoding="utf-8"
    )
    monkeypatch.setattr(audit_run, "REPO_ROOT", repo)
    r = audit_run.check_trust_boundary_coverage()
    assert r.status == "fail"
    assert "S42" in r.extra["missing"][0]


# --- Aggregation + CLI ------------------------------------------------------


def test_render_report_totals() -> None:
    results = [
        audit_run.CheckResult(name="a", status="pass", returncode=0, duration_seconds=0.1),
        audit_run.CheckResult(name="b", status="fail", returncode=1, duration_seconds=0.2),
        audit_run.CheckResult(name="c", status="skipped", returncode=None, duration_seconds=0.0),
    ]
    rep = audit_run.render_report(results)
    assert rep["totals"]["pass"] == 1
    assert rep["totals"]["fail"] == 1
    assert rep["totals"]["skipped"] == 1
    assert len(rep["checks"]) == 3


def test_run_checks_only_filter() -> None:
    def fake_pass(*args, **kwargs):
        return audit_run.CheckResult(
            name="ruff", status="pass", returncode=0, duration_seconds=0.01
        )

    with patch.object(audit_run, "check_ruff", fake_pass):
        results = audit_run.run_checks(only=["ruff"])
    assert [r.name for r in results] == ["ruff"]


def test_run_checks_unknown_name_marked_skipped() -> None:
    results = audit_run.run_checks(only=["does-not-exist"])
    assert len(results) == 1
    assert results[0].status == "skipped"
    assert "Unbekannter Check" in results[0].stderr_tail


def test_main_returns_0_when_all_pass(capsys: pytest.CaptureFixture[str]) -> None:
    def pass_check():
        return audit_run.CheckResult(name="ruff", status="pass", returncode=0, duration_seconds=0.01)

    with patch.dict(audit_run._ALL_CHECKS, {"ruff": pass_check}, clear=True):
        rc = audit_run.main(["--only", "ruff"])
    assert rc == 0


def test_main_returns_1_when_any_fail(capsys: pytest.CaptureFixture[str]) -> None:
    def fail_check():
        return audit_run.CheckResult(name="ruff", status="fail", returncode=1, duration_seconds=0.01)

    with patch.dict(audit_run._ALL_CHECKS, {"ruff": fail_check}, clear=True):
        rc = audit_run.main(["--only", "ruff"])
    assert rc == 1
