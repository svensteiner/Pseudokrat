"""Tests fuer den fail-closed PDF-Pfad (Council #1):
- Normale PDF wird sauber geschwaerzt (kein Rest).
- Wort-Sequenz-Fallback findet mehrteilige PII.
- Nicht lokalisierbare erkannte PII -> ResidualPIIError, KEINE Ausgabe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat import watcher

pymupdf = pytest.importorskip("pymupdf")


def _make_pdf(path: Path, text: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _build_anon(store_and_audit):  # noqa: ANN001
    from pseudokrat.anonymizer import Anonymizer
    from pseudokrat.recognizers import recognizers_for_store

    store, audit = store_and_audit
    return (
        Anonymizer(
            store=store,
            recognizers=recognizers_for_store(store),
            detector=None,
            audit_log=audit,
            model_version="disabled",
        ),
        store,
    )


class TestFailClosed:
    def test_normal_pdf_redacted_no_residual(self, tmp_path, store_and_audit) -> None:  # noqa: ANN001
        anon, store = _build_anon(store_and_audit)
        src = tmp_path / "in.pdf"
        _make_pdf(src, "Hofer Bau GmbH zahlt heute.")
        out = tmp_path / "out.pdf"
        watcher.redact_pdf(src, out, anon, store, remove_logos=True, ocr=None, log=lambda _m: None)
        text = "".join(p.get_text() for p in pymupdf.open(str(out)))
        assert "Hofer Bau GmbH" not in text
        assert "<COMPANY_" in text

    def test_unlocatable_pii_raises_and_writes_nothing(
        self, tmp_path, store_and_audit, monkeypatch
    ) -> None:  # noqa: ANN001
        anon, store = _build_anon(store_and_audit)
        src = tmp_path / "in.pdf"
        _make_pdf(src, "Hofer Bau GmbH zahlt heute.")
        out = tmp_path / "out.pdf"

        # Erkennung funktioniert, aber Lokalisierung schlaegt fehl -> fail-closed.
        monkeypatch.setattr(watcher, "_pii_rect_groups", lambda *a, **k: [])

        with pytest.raises(watcher.ResidualPIIError):
            watcher.redact_pdf(
                src, out, anon, store, remove_logos=False, ocr=None, log=lambda _m: None
            )
        assert not out.exists()  # KEINE Ausgabe geschrieben

    def test_deanon_reports_unknown_placeholder(self, tmp_path, store_and_audit) -> None:  # noqa: ANN001
        from pseudokrat.deanonymizer import Deanonymizer

        store, audit = store_and_audit
        de = Deanonymizer(store=store, audit_log=audit, model_version="disabled")
        src = tmp_path / "rev.pdf"
        _make_pdf(src, "Bericht der <COMPANY_999>.")  # nicht im Store
        out = tmp_path / "rev.out.pdf"
        resolved, missing = watcher.deanon_pdf(src, out, de)
        assert missing == 1
        assert resolved == 0

    def test_single_page_top_logo_removed(self, tmp_path, store_and_audit) -> None:  # noqa: ANN001
        anon, store = _build_anon(store_and_audit)
        doc = pymupdf.open()
        page = doc.new_page()  # A4 ~595x842
        page.insert_text((72, 400), "Rechnung ohne PII.")
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 24))
        pix.clear_with(180)
        page.insert_image(pymupdf.Rect(60, 20, 260, 70), pixmap=pix)  # Briefkopf (<252)
        src = tmp_path / "logo.pdf"
        doc.save(str(src))
        doc.close()
        out = tmp_path / "logo.out.pdf"
        watcher.redact_pdf(src, out, anon, store, remove_logos=True, ocr=None, log=lambda _m: None)
        result = pymupdf.open(str(out))
        assert len(result[0].get_images()) == 0  # Briefkopf-Bild entfernt
        result.close()

    def test_single_page_body_image_kept(self, tmp_path, store_and_audit) -> None:  # noqa: ANN001
        anon, store = _build_anon(store_and_audit)
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Text ohne PII.")
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 24))
        pix.clear_with(180)
        page.insert_image(pymupdf.Rect(60, 400, 260, 460), pixmap=pix)  # Textkoerper (>252)
        src = tmp_path / "body.pdf"
        doc.save(str(src))
        doc.close()
        out = tmp_path / "body.out.pdf"
        watcher.redact_pdf(src, out, anon, store, remove_logos=True, ocr=None, log=lambda _m: None)
        result = pymupdf.open(str(out))
        assert len(result[0].get_images()) == 1  # Inhaltsbild bleibt erhalten
        result.close()

    def test_word_fallback_finds_multitoken(self, tmp_path) -> None:  # noqa: ANN001
        # get_text('words') liefert die Woerter; Fallback baut die Gruppe.
        src = tmp_path / "w.pdf"
        _make_pdf(src, "Firma Alpen Handel GmbH hier.")
        doc = pymupdf.open(str(src))
        page = doc[0]

        class _NoSearch:
            def __getattr__(self, name):
                return getattr(page, name)

            def search_for(self, *_a, **_k):
                return []  # search_for kuenstlich blockieren

        groups = watcher._pii_rect_groups(_NoSearch(), "Alpen Handel GmbH", pymupdf)
        assert groups and len(groups[0]) == 3  # drei Wort-Rechtecke
        doc.close()
