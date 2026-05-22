"""Tests für den UI-freien GUI-Controller."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.gui.controller import GuiController, GuiError, PreviewSpan


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PSEUDOKRAT_DISABLE_ML", "1")


def test_open_anonymize_deanonymize_roundtrip() -> None:
    ctrl = GuiController()
    ctrl.open_profile("gui1", "pw")
    try:
        anonymized, counts = ctrl.anonymize("Hofer Bau GmbH ist Mandant.")
        assert "<COMPANY_001>" in anonymized
        assert counts.get("COMPANY", 0) == 1

        restored, resolved, missing = ctrl.deanonymize(anonymized)
        assert "Hofer Bau GmbH" in restored
        assert resolved == 1
        assert missing == 0
    finally:
        ctrl.close()


def test_open_profile_empty_name_raises() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.open_profile("", "pw")


def test_open_profile_empty_password_raises() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.open_profile("p", "")


def test_open_profile_wrong_password_raises() -> None:
    ctrl = GuiController()
    ctrl.open_profile("p", "rightpw")
    ctrl.close()
    with pytest.raises(GuiError):
        ctrl.open_profile("p", "wrongpw")


def test_anonymize_without_session_raises() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.anonymize("foo")
    with pytest.raises(GuiError):
        ctrl.deanonymize("foo")
    with pytest.raises(GuiError):
        ctrl.verify_audit()


def test_list_profiles_after_open() -> None:
    ctrl = GuiController()
    ctrl.open_profile("alpha", "pw")
    ctrl.close()
    ctrl.open_profile("beta", "pw")
    ctrl.close()
    names = ctrl.list_profiles()
    assert "alpha" in names
    assert "beta" in names


def test_preview_without_session_raises() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.preview("egal")


def test_preview_returns_sorted_spans_without_mutating_store() -> None:
    ctrl = GuiController()
    ctrl.open_profile("preview", "pw")
    try:
        sample = "Hofer Bau GmbH (UID ATU12345675) zahlt auf AT611904300234573201."
        spans = ctrl.preview(sample)

        # in start-Reihenfolge, mit den drei erwarteten Kategorien
        assert spans == sorted(spans, key=lambda s: s.start)
        categories = {s.category for s in spans}
        assert {"COMPANY", "UID", "IBAN"}.issubset(categories)

        for span in spans:
            assert isinstance(span, PreviewSpan)
            assert 0 <= span.start < span.end <= len(sample)
            assert sample[span.start : span.end] == span.text
            assert 0.0 <= span.score <= 1.0

        # Vorschau darf das Mapping nicht persistieren — Folge-anonymize() startet
        # bei _001, nicht weiter unten.
        anonymized, _ = ctrl.anonymize(sample)
        assert "<COMPANY_001>" in anonymized
    finally:
        ctrl.close()


def test_preview_empty_text_returns_empty() -> None:
    ctrl = GuiController()
    ctrl.open_profile("preview_empty", "pw")
    try:
        assert ctrl.preview("") == []
        assert ctrl.preview("Nur Klartext ohne PII.") == []
    finally:
        ctrl.close()


def test_verify_audit_after_anonymize() -> None:
    ctrl = GuiController()
    ctrl.open_profile("audit", "pw")
    try:
        ctrl.anonymize("Hofer Bau GmbH.")
        assert ctrl.verify_audit() is True
    finally:
        ctrl.close()


def test_open_profile_replaces_previous_session() -> None:
    ctrl = GuiController()
    ctrl.open_profile("first", "pw")
    first = ctrl.session
    ctrl.open_profile("second", "pw")
    assert ctrl.session is not None
    assert ctrl.session.profile_name == "second"
    assert ctrl.session is not first
    ctrl.close()


def test_process_file_without_session_raises(tmp_path: Path) -> None:
    ctrl = GuiController()
    sample = tmp_path / "x.txt"
    sample.write_text("egal", encoding="utf-8")
    with pytest.raises(GuiError):
        ctrl.process_file(sample)


def test_process_file_missing_input_raises(tmp_path: Path) -> None:
    ctrl = GuiController()
    ctrl.open_profile("pf_missing", "pw")
    try:
        with pytest.raises(GuiError):
            ctrl.process_file(tmp_path / "does_not_exist.txt")
    finally:
        ctrl.close()


def test_process_file_unsupported_format_raises(tmp_path: Path) -> None:
    ctrl = GuiController()
    ctrl.open_profile("pf_unsupp", "pw")
    sample = tmp_path / "weird.dat"
    sample.write_bytes(b"\x00\x01")
    try:
        with pytest.raises(GuiError):
            ctrl.process_file(sample)
    finally:
        ctrl.close()


def test_process_file_txt_roundtrip(tmp_path: Path) -> None:
    ctrl = GuiController()
    ctrl.open_profile("pf_txt", "pw")
    try:
        src = tmp_path / "brief.txt"
        src.write_text("Hofer Bau GmbH ist unser Mandant.", encoding="utf-8")
        anon = ctrl.process_file(src)
        assert anon.output_path.exists()
        anonymized = anon.output_path.read_text(encoding="utf-8")
        assert "<COMPANY_001>" in anonymized
        assert "Hofer Bau GmbH" not in anonymized
        # Original unangetastet
        assert src.read_text(encoding="utf-8") == "Hofer Bau GmbH ist unser Mandant."

        # Deanonymize the anonymized output
        deanon = ctrl.process_file(anon.output_path, deanonymize=True)
        restored = deanon.output_path.read_text(encoding="utf-8")
        assert "Hofer Bau GmbH" in restored
    finally:
        ctrl.close()


def test_process_file_explicit_output_path(tmp_path: Path) -> None:
    ctrl = GuiController()
    ctrl.open_profile("pf_out", "pw")
    try:
        src = tmp_path / "in.txt"
        src.write_text("Hofer Bau GmbH.", encoding="utf-8")
        target = tmp_path / "subdir" / "out.txt"
        result = ctrl.process_file(src, output_path=target)
        assert result.output_path == target
        assert target.exists()
        assert "<COMPANY_001>" in target.read_text(encoding="utf-8")
    finally:
        ctrl.close()


def test_supported_file_suffixes_nonempty() -> None:
    ctrl = GuiController()
    suffixes = ctrl.supported_file_suffixes()
    assert ".txt" in suffixes
    assert ".csv" in suffixes


def test_list_profile_summaries_empty() -> None:
    ctrl = GuiController()
    summaries = ctrl.list_profile_summaries()
    assert summaries == []


def test_list_profile_summaries_after_anonymize() -> None:
    ctrl = GuiController()
    ctrl.open_profile("summary_a", "pw")
    try:
        ctrl.anonymize("Hofer Bau GmbH ist Mandant.")
    finally:
        ctrl.close()
    ctrl.open_profile("summary_b", "pw")
    ctrl.close()

    summaries = ctrl.list_profile_summaries()
    names = {s.name for s in summaries}
    assert names == {"summary_a", "summary_b"}

    by_name = {s.name: s for s in summaries}
    assert by_name["summary_a"].mapping_count == 1
    assert by_name["summary_b"].mapping_count == 0
    assert by_name["summary_a"].created_utc != ""
    assert by_name["summary_a"].db_path.exists()


def test_create_profile_requires_name() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.create_profile("", "pw")


def test_create_profile_requires_password() -> None:
    ctrl = GuiController()
    with pytest.raises(GuiError):
        ctrl.create_profile("new_profile", "")


def test_create_profile_rejects_duplicate() -> None:
    ctrl = GuiController()
    ctrl.create_profile("dup_profile", "pw")
    with pytest.raises(GuiError):
        ctrl.create_profile("dup_profile", "pw")


def test_create_profile_does_not_replace_open_session() -> None:
    ctrl = GuiController()
    ctrl.open_profile("active", "pw")
    try:
        ctrl.create_profile("freshly_created", "pw")
        # Active session bleibt erhalten
        assert ctrl.session is not None
        assert ctrl.session.profile_name == "active"
    finally:
        ctrl.close()
    names = {s.name for s in ctrl.list_profile_summaries()}
    assert "freshly_created" in names
    assert "active" in names
