"""Tests fuer den HTML-Handler.

HTML wird als Text anonymisiert: Firmenname im <title>, E-Mails/URLs in
Attributen (href, …) und im Fliesstext werden ersetzt — typische Leck-Stellen
bei Viewer-/Report-Exporten.
"""

from __future__ import annotations

from pathlib import Path

from pseudokrat.formats import HtmlHandler, handler_for


def _transform_mask(text: str) -> str:
    # Minimaler, deterministischer Transform: ersetzt die Test-PII.
    return (
        text.replace("Muster Handel GmbH", "<COMPANY_001>")
        .replace("max.mustermann@muster.example.com", "<EMAIL_001>")
        .replace("office@muster-handel.at", "<EMAIL_002>")
    )


HTML = (
    "<html><head><title>Muster Handel GmbH - JA</title></head>\n"
    "<body><p>Bericht der Muster Handel GmbH.</p>\n"
    '<a href="https://x/?u=max.mustermann@muster.example.com">V</a>\n'
    "<p>office@muster-handel.at</p></body></html>\n"
)


class TestHtmlHandlerRouting:
    def test_handler_for_html(self) -> None:
        assert isinstance(handler_for(Path("seite.html")), HtmlHandler)

    def test_handler_for_htm(self) -> None:
        assert isinstance(handler_for(Path("seite.htm")), HtmlHandler)


class TestHtmlAnonymization:
    def test_title_url_email_masked(self, tmp_path: Path) -> None:
        src = tmp_path / "bericht.html"
        src.write_text(HTML, encoding="utf-8")
        dst = tmp_path / "bericht.anon.html"

        HtmlHandler().process(src, dst, transform=_transform_mask)
        out = dst.read_text(encoding="utf-8")

        assert "Muster Handel GmbH" not in out
        assert "max.mustermann@muster.example.com" not in out
        assert "office@muster-handel.at" not in out
        # Titel-Tag bleibt erhalten, nur der Name ist ersetzt.
        assert "<title><COMPANY_001> - JA</title>" in out
        assert "<EMAIL_001>" in out

    def test_latin1_fallback_does_not_crash(self, tmp_path: Path) -> None:
        src = tmp_path / "alt.html"
        src.write_bytes("<p>Gr\xfc\xdfe</p>".encode("latin-1"))
        dst = tmp_path / "alt.anon.html"
        # Darf nicht mit UnicodeDecodeError abbrechen.
        HtmlHandler().process(src, dst, transform=lambda t: t)
        assert dst.exists()
