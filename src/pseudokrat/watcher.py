"""Ordner-Watcher — installationsfreie Drop-Folder-Anonymisierung.

Diese Schiene braucht **keinen** Registry-Eingriff und keine Admin-Rechte —
gedacht fuer Rechner, auf denen die IT Installationen blockiert. Sie ueberwacht
einen Basis-Ordner mit folgenden Unterordnern (werden automatisch angelegt):

* ``INPUT``           — Datei hineinlegen  → wird anonymisiert
* ``OUTPUT``          — anonymisiertes Ergebnis
* ``ZURUECK_INPUT``   — KI-Antwort mit Platzhaltern hineinlegen → rueckuebersetzt
* ``ZURUECK_OUTPUT``  — Klartext (Originale wiederhergestellt)
* ``Verarbeitet``     — Originale nach erfolgreicher Verarbeitung
* ``Fehler``          — Dateien, die nicht verarbeitet werden konnten

Zusatzdatei ``Begriffe.txt`` im Basis-Ordner: mandanten-spezifische Begriffe
(ein Begriff pro Zeile), die ueberall — auch in Bildern — ersetzt werden.

PDF-Besonderheiten (layout-erhaltend):
* PII-Text wird im Original ueberschrieben, Tabellen/Zahlen/Layout bleiben.
* Logos (Bilder, die auf mehreren Seiten wiederkehren) werden entfernt.
* Text in Bildern (z. B. als Bild eingebettete Tabellen) wird per OCR gefunden
  und geschwaerzt — sofern das optionale OCR-Paket installiert ist.

Optionale Abhaengigkeiten:
* ``pip install pseudokrat[watcher]`` → PyMuPDF (layout-erhaltende PDF-Redaction)
* ``pip install pseudokrat[ocr]``     → RapidOCR (Text in Bildern)
"""

from __future__ import annotations

import contextlib
import re
import shutil
import time
from pathlib import Path
from typing import Any, cast

#: Dateiendungen, die der Watcher verarbeitet.
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".tsv", ".md", ".log", ".html", ".htm"}
)

#: Platzhalter-Muster fuer die PDF-Rueckuebersetzung.
_PLACEHOLDER_RE = re.compile(r"<[A-Z_]+_\d{3,}>")


# --------------------------------------------------------------------------- #
#  Eigene Begriffe (Begriffe.txt)
# --------------------------------------------------------------------------- #


_TERMS_TEMPLATE = """\
# Begriffe.txt — eigene Begriffe, die IMMER anonymisiert werden.
#
# Ein Begriff pro Zeile. Gross-/Kleinschreibung egal.
# Zeilen, die mit # beginnen, sind Kommentare und werden ignoriert.
#
# Trage hier Namen/Marken/Domains ein, die das Tool nicht von selbst
# erkennt (z. B. Firmen-Kurznamen, Projektnamen, Web-Adressen).
#
# Aenderungen wirken beim naechsten Start (Fenster schliessen und neu starten).

# Beispiele (bitte anpassen oder loeschen):
# Mustermann GmbH
# ProjektXY
# beispiel.at
"""


def ensure_terms_template(path: Path) -> bool:
    """Legt eine kommentierte ``Begriffe.txt`` an, falls sie fehlt.

    Gibt ``True`` zurueck, wenn die Datei neu erstellt wurde. Eine bereits
    vorhandene Datei (mit echten Begriffen) wird nie ueberschrieben.
    """
    if path.exists():
        return False
    path.write_text(_TERMS_TEMPLATE, encoding="utf-8")
    return True


def load_terms(path: Path) -> list[str]:
    """Liest mandanten-spezifische Begriffe (eine Zeile pro Begriff, ``#`` = Kommentar).

    Robust gegen Kodierung (UTF-8 mit/ohne BOM, sonst Windows-1252). Begriffe
    mit weniger als 2 Zeichen werden ignoriert — ein Ein-Zeichen-Begriff wuerde
    praktisch den ganzen Text schwaerzen.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="cp1252", errors="replace")
    terms: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) >= 2:
            terms.append(stripped)
    return terms


class TermRecognizer:
    """Erkennt frei konfigurierte Begriffe (case-insensitiv). Platzhalter: ``<BEGRIFF_xxx>``."""

    name = "begriffe"

    def __init__(self, terms: list[str]) -> None:
        self._patterns = [re.compile(re.escape(t), re.IGNORECASE) for t in terms if t]

    def analyze(self, text: str) -> list[Span]:
        from pseudokrat.recognizers.base import Span

        spans: list[Span] = []
        for pattern in self._patterns:
            for match in pattern.finditer(text):
                if match.end() > match.start():
                    spans.append(
                        Span(
                            start=match.start(),
                            end=match.end(),
                            category="BEGRIFF",
                            text=match.group(0),
                            score=1.0,
                        )
                    )
        return spans


# --------------------------------------------------------------------------- #
#  PDF — layout-erhaltende Redaction + Logo-Entfernung + OCR
# --------------------------------------------------------------------------- #


def _require_pymupdf() -> Any:
    try:
        import pymupdf  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - abh. von Optional-Install
        raise RuntimeError(
            "PDF-Verarbeitung benoetigt PyMuPDF. Installation: "
            "pip install 'pseudokrat[watcher]'"
        ) from exc
    return pymupdf


class _OcrEngine:
    """Lazy-Wrapper um RapidOCR (laedt die Modelle erst beim ersten Bild)."""

    def __init__(self, log: Any) -> None:
        self._log = log
        self._engine: Any = None
        self._unavailable = False

    def read(self, image_bytes: bytes) -> list[Any] | None:
        if self._unavailable:
            return None
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]
            except ImportError:
                self._log(
                    "     (OCR nicht installiert — Text in Bildern wird NICHT geprueft. "
                    "Installation: pip install 'pseudokrat[ocr]')"
                )
                self._unavailable = True
                return None
            self._log("Lade OCR-Modelle (einmalig, dauert kurz) ...")
            self._engine = RapidOCR()
        result, _elapsed = self._engine(image_bytes)
        return cast("list[Any] | None", result)


class ResidualPIIError(RuntimeError):
    """Erkannte PII konnte nicht sicher entfernt/geschwaerzt werden.

    Wird geworfen, damit der Watcher die Ausgabe NICHT freigibt (fail-closed):
    lieber eine Datei im Fehler-Ordner als ein stilles Klartext-Leck Richtung
    Cloud-KI. Die Nachricht enthaelt bewusst KEINEN Klartext (nur Anzahl).
    """

    def __init__(self, count: int) -> None:
        super().__init__(
            f"PII erkannt, aber {count} Stelle(n) im Layout nicht sicher "
            "schwaerzbar — Ausgabe nicht freigegeben (fail-closed)."
        )
        self.count = count


def _pii_rect_groups(page: Any, original: str, pymupdf: Any) -> list[list[Any]]:
    """Findet die zu schwaerzenden Rechteck-Gruppen fuer einen PII-String.

    Erst ``search_for`` (schnell, eine Gruppe je Vorkommen). Wenn das nichts
    liefert (Text ueber Zeilenumbruch/fragmentiert), Fallback ueber die
    Wort-Sequenz: aufeinanderfolgende Woerter, deren Texte exakt den Tokens
    des PII-Strings entsprechen, bilden eine Gruppe (mehrere Rechtecke).
    """
    direct = list(page.search_for(original))
    if direct:
        return [[r] for r in direct]

    target = original.split()
    if not target:
        return []
    words = page.get_text("words")  # (x0,y0,x1,y1, wort, block, line, wortnr)
    n = len(target)
    groups: list[list[Any]] = []
    i = 0
    while i <= len(words) - n:
        window = words[i : i + n]
        if [w[4] for w in window] == target:
            groups.append([pymupdf.Rect(w[0], w[1], w[2], w[3]) for w in window])
            i += n
        else:
            i += 1
    return groups


def redact_pdf(
    src: Path,
    dst: Path,
    anonymizer: Anonymizer,
    store: Any,
    *,
    remove_logos: bool,
    ocr: _OcrEngine | None,
    log: Any,
    counts: dict[str, int] | None = None,
) -> int:
    """Anonymisiert eine PDF layout-erhaltend. Gibt die Anzahl Treffer zurueck.

    Fail-closed: kann erkannte PII nicht lokalisiert/geschwaerzt werden, wird
    :class:`ResidualPIIError` geworfen und KEINE Ausgabe geschrieben. ``counts``
    wird (falls übergeben) pro Kategorie mit den Treffern befüllt.
    """
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(src))
    hits = 0
    unresolved = 0  # erkannte PII, die nicht lokalisiert werden konnte
    try:
        # Logos = Bilder, die auf >= 2 Seiten vorkommen (Briefkopf/Logo).
        page_count: dict[int, int] = {}
        for page in doc:
            for xref in {img[0] for img in page.get_images(full=True)}:
                page_count[xref] = page_count.get(xref, 0) + 1
        logo_xrefs = {x for x, c in page_count.items() if c >= 2}

        n_pages = doc.page_count
        for page_index, page in enumerate(doc, start=1):
            if n_pages > 3:
                log(f"     Seite {page_index} von {n_pages} ...")
            # 0) OCR: Text in (Nicht-Logo-)Bildern finden und im Bild schwaerzen.
            if ocr is not None:
                hits += _ocr_redact_images(page, doc, logo_xrefs, anonymizer, ocr, log)

            # 1) Text-PII ersetzen (Bilder bleiben unangetastet).
            text = page.get_text()
            if text.strip():
                result = anonymizer.anonymize(text)
                if counts is not None:
                    for cat, num in result.entity_counts.items():
                        counts[cat] = counts.get(cat, 0) + num
                pairs: dict[str, str] = {}
                for span in result.spans:
                    pairs[span.text] = store.get_or_create(
                        span.text, span.category
                    ).placeholder
                for original in sorted(pairs, key=len, reverse=True):
                    placeholder = pairs[original]
                    groups = _pii_rect_groups(page, original, pymupdf)
                    if not groups:
                        # Erkannt, aber nicht auffindbar -> fail-closed (s.u.).
                        unresolved += 1
                        continue
                    for group in groups:
                        # Platzhalter nur ins erste Rechteck; Folge-Rechtecke
                        # (Zeilenumbruch) nur weiss ausfuellen.
                        for idx, rect in enumerate(group):
                            page.add_redact_annot(
                                rect,
                                text=placeholder if idx == 0 else "",
                                fontname="helv",
                                fontsize=max(4.0, min(11.0, rect.height * 0.8)),
                                fill=(1, 1, 1),
                                text_color=(0, 0, 0),
                                cross_out=False,
                            )
                            hits += 1
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)

            # 2) Logos entfernen (nur wiederkehrende Bilder).
            if remove_logos and logo_xrefs:
                removed = False
                for xref in logo_xrefs:
                    for rect in page.get_image_rects(xref):
                        page.add_redact_annot(rect, fill=(1, 1, 1))
                        hits += 1
                        removed = True
                if removed:
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE)

        # FAIL-CLOSED: konnte erkannte PII nicht lokalisiert/geschwaerzt werden,
        # NICHT nach OUTPUT schreiben — lieber Fehler-Ordner als stilles Leck.
        if unresolved:
            raise ResidualPIIError(unresolved)

        # Versteckte PDF-Kanaele bereinigen: Annotationen (Kommentare/Notizen/
        # Formularfelder), eingebettete Anhaenge und Lesezeichen/Gliederung —
        # alle koennen Klartext-Namen enthalten, die die Redaction nicht sieht.
        for page in doc:
            for annot in list(page.annots() or []):
                with contextlib.suppress(Exception):
                    page.delete_annot(annot)
        with contextlib.suppress(Exception):
            for name in list(doc.embfile_names()):
                doc.embfile_del(name)
        with contextlib.suppress(Exception):
            doc.set_toc([])

        # Dokument-Eigenschaften entfernen: /Title /Author /Subject /Keywords
        # /Creator /Producer sowie XMP-Metadaten (enthalten oft Mandant/Verfasser).
        # Metadaten duerfen den Lauf nicht stoppen -> Fehler bewusst schlucken.
        with contextlib.suppress(Exception):
            doc.set_metadata({})
        with contextlib.suppress(Exception):
            doc.set_xml_metadata("")

        doc.save(str(dst), garbage=4, deflate=True)
    finally:
        doc.close()
    return hits


_OCR_LEGAL_FORM_BOUNDARY_RE = re.compile(
    r"(?<=[A-Za-z])(?=(?:GmbH|AG|KG|OG|OHG|UG|SE|KGaA|Ltd\.?|Inc\.?|Corp\.?|LLC)\b)"
)
_OCR_STREET_FRAGMENT_RE = re.compile(
    r"\b[A-Z][A-Za-z' -]{2,}"
    r"(?:strasse|strabe|gasse|allee|weg|platz|ring|promenade|anlage|park|street|road)"
    r"\s+\d{1,4}[A-Za-z]?\b",
    re.IGNORECASE,
)
_OCR_POSTAL_CITY_RE = re.compile(
    r"\b(?:[A-Z]{1,3}\s*[-\u2013\u2014]\s*)?\d{4,5}\s+"
    r"[A-Z][A-Za-z' -]{2,}\b",
    re.IGNORECASE,
)


def _ocr_detection_variants(text: str) -> list[str]:
    """Return OCR-normalized text variants used only for detection decisions."""
    normalized = (
        text.replace("StraBe", "Strasse")
        .replace("straBe", "strasse")
        .replace("Stra8e", "Strasse")
        .replace("stra8e", "strasse")
        .replace("\u03b2", "ss")
    )
    normalized = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", normalized)
    spaced = _OCR_LEGAL_FORM_BOUNDARY_RE.sub(" ", normalized)
    variants = [normalized]
    for candidate in (
        spaced,
        re.sub(r"(?<=[a-z])(?=[A-Z])", " ", normalized),
        normalized.replace("'", " "),
    ):
        if candidate != normalized and candidate not in variants:
            variants.append(candidate)
    return variants


def _ocr_text_has_pii(text: str, anonymizer: Anonymizer) -> bool:
    if anonymizer.detect(text):
        return True
    for variant in _ocr_detection_variants(text):
        if variant != text and anonymizer.detect(variant):
            return True
        if _OCR_STREET_FRAGMENT_RE.search(variant):
            return True
        if _OCR_POSTAL_CITY_RE.search(variant):
            return True
    return False


def _ocr_redact_images(
    page: Any,
    doc: Any,
    logo_xrefs: set[int],
    anonymizer: Anonymizer,
    ocr: _OcrEngine,
    log: Any,
) -> int:
    """OCR'd jedes Nicht-Logo-Bild, schwaerzt PII-Treffer direkt im Bild."""
    import io

    from PIL import Image, ImageDraw

    hits = 0
    for img in page.get_images(full=True):
        xref = img[0]
        if xref in logo_xrefs:
            continue
        try:
            base = doc.extract_image(xref)
            pil = Image.open(io.BytesIO(base["image"])).convert("RGB")
        except Exception:  # noqa: BLE001 - defektes/unlesbares Bild ueberspringen
            continue
        if pil.width < 40 or pil.height < 20:
            continue
        try:
            ocr_result = ocr.read(base["image"])
        except Exception as exc:  # noqa: BLE001
            log(f"     (OCR-Fehler bei xref={xref}: {exc})")
            continue
        if not ocr_result:
            continue
        draw = ImageDraw.Draw(pil)
        changed = False
        for box, txt, _score in ocr_result:
            if not txt or not _ocr_text_has_pii(txt, anonymizer):
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            draw.rectangle([min(xs), min(ys), max(xs), max(ys)], fill=(0, 0, 0))
            changed = True
            hits += 1
        if changed:
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            try:
                page.replace_image(xref, stream=buf.getvalue())
            except Exception as exc:  # noqa: BLE001
                log(f"     (Bild-Ersetzung fehlgeschlagen xref={xref}: {exc})")
    return hits


def deanon_pdf(src: Path, dst: Path, deanonymizer: Deanonymizer) -> tuple[int, int]:
    """Rueckuebersetzung in einer PDF. Gibt (zurueckgesetzt, unbekannt) zurueck.

    ``unbekannt`` = Platzhalter, die im aktuellen Profil-Store nicht aufloesbar
    sind (z. B. falsches Profil / fremder Store) — werden sichtbar gemacht,
    statt still stehen zu bleiben.
    """
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(src))
    resolved = 0
    missing = 0
    try:
        for page in doc:
            text = page.get_text()
            for placeholder in set(_PLACEHOLDER_RE.findall(text)):
                original = deanonymizer.deanonymize(placeholder).text
                if original == placeholder:
                    missing += 1  # im Store unbekannt
                    continue
                for group in _pii_rect_groups(page, placeholder, pymupdf):
                    for idx, rect in enumerate(group):
                        page.add_redact_annot(
                            rect,
                            text=original if idx == 0 else "",
                            fontname="helv",
                            fontsize=max(4.0, min(11.0, rect.height * 0.8)),
                            fill=(1, 1, 1),
                            text_color=(0, 0, 0),
                            cross_out=False,
                        )
                        resolved += 1
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
        doc.save(str(dst), garbage=4, deflate=True)
    finally:
        doc.close()
    return resolved, missing


# --------------------------------------------------------------------------- #
#  Watcher-Hauptschleife
# --------------------------------------------------------------------------- #


def _file_is_stable(path: Path) -> bool:
    """True, wenn die Datei fertig geschrieben ist (Groesse zwei Messungen gleich)."""
    try:
        size1 = path.stat().st_size
        time.sleep(0.8)
        return size1 == path.stat().st_size
    except OSError:
        return False


#: In Windows-Dateinamen unzulaessige Zeichen (inkl. der Platzhalter-Klammern).
_FILENAME_BAD = '<>:"/\\|?*'


def safe_anonymized_stem(stem: str, anonymizer: Anonymizer) -> str:
    """Anonymisiert einen Dateinamen-Stamm und macht ihn Windows-sicher.

    Erkannte PII (Firmen, Namen, eigene Begriffe …) wird durch Platzhalter
    ersetzt; die Platzhalter-Klammern ``<>`` und andere unzulaessige Zeichen
    werden entschaerft. So enthaelt der Ausgabe-Dateiname keinen Klartext mehr.
    """
    anonymized = anonymizer.anonymize(stem).text
    for ch in _FILENAME_BAD:
        anonymized = anonymized.replace(ch, "_" if ch not in "<>" else "")
    cleaned = "_".join(anonymized.split())  # Whitespace zusammenfassen
    return cleaned.strip("_") or "dokument"


def strip_office_metadata(path: Path) -> None:
    """Entfernt Dokument-Eigenschaften aus XLSX/DOCX/PPTX (Office Open XML).

    Schreibt ``docProps/core.xml`` und ``docProps/app.xml`` neutral neu
    (Autor, Titel, Firma, "Zuletzt gespeichert von" … verschwinden).
    """
    import zipfile

    suffix = path.suffix.lower()
    if suffix not in (".xlsx", ".docx", ".pptx"):
        return

    neutral = {
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "</cp:coreProperties>"
        ),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties '
            'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "</Properties>"
        ),
        # Benutzerdefinierte Eigenschaften (oft Mandant/Projekt/Ersteller).
        "docProps/custom.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties '
            'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            "</Properties>"
        ),
    }

    # customXml/itemN.xml enthaelt oft eingebettete Kunden-Daten (z. B.
    # SharePoint-/Content-Control-Bindungen). Inhalt leeren statt loeschen —
    # so bleiben Relationships intakt (kein Reparatur-Dialog), die Daten weg.
    custom_item_re = re.compile(r"^customXml/item\d+\.xml$")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path, "r") as zin, zipfile.ZipFile(
        tmp, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            fname = item.filename
            data = neutral.get(fname)
            if data is not None:
                zout.writestr(fname, data)
            elif custom_item_re.match(fname):
                zout.writestr(fname, "<root/>")
            else:
                zout.writestr(item, zin.read(fname))
    tmp.replace(path)


#: PII-Kategorie -> deutsches Label für den Ergebnis-Bericht.
_CATEGORY_LABELS: dict[str, str] = {
    "IBAN": "IBAN", "CREDITCARD": "Kreditkarte", "UID": "UID", "SVNR": "SVNR",
    "STEUERNR": "Steuernr", "FN": "Firmenbuch", "TAX_ID": "Steuer-ID",
    "AHV": "AHV", "BIC": "BIC", "COMPANY": "Firma", "PERSON": "Person",
    "ADDRESS": "Adresse", "EMAIL": "E-Mail", "PHONE": "Telefon", "URL": "URL",
    "SECRET": "Schluessel", "BEGRIFF": "Begriff", "MANDANT_NR": "Mandantennr",
    "BIRTHDATE": "Geburtsdatum",
}


def _format_counts(counts: dict[str, int]) -> str:
    """'3x IBAN, 2x Firma, 1x E-Mail' aus einem Kategorie-Zähler."""
    parts = [
        f"{n}x {_CATEGORY_LABELS.get(cat, cat)}"
        for cat, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if n
    ]
    return ", ".join(parts) if parts else "0 Treffer"


def _friendly_error(exc: Exception) -> str:
    """Erklärung in einfachem Deutsch, was der Nutzer tun kann."""
    from pseudokrat.formats import UnsupportedFormatError

    if isinstance(exc, ResidualPIIError):
        return (
            "Es wurde etwas Identifizierendes gefunden, das an dieser Stelle "
            "nicht sicher geschwaerzt werden konnte. Die Datei wurde daher NICHT "
            "freigegeben (Sicherheit vor Bequemlichkeit). Bitte die Datei pruefen "
            "oder als PDF/Excel neu exportieren und erneut in INPUT legen."
        )
    if isinstance(exc, PermissionError):
        return (
            "Die Datei war vermutlich noch in Word/Excel/Adobe geoeffnet oder "
            "wurde noch kopiert. Bitte schliessen und erneut in INPUT ziehen."
        )
    if isinstance(exc, UnsupportedFormatError):
        return (
            "Dieses Dateiformat wird (noch) nicht unterstuetzt. Unterstuetzt: "
            "PDF, Word (.docx), Excel (.xlsx), CSV, TXT, HTML."
        )
    return (
        "Die Datei konnte nicht verarbeitet werden. Bitte pruefen, ob sie "
        "beschaedigt oder passwortgeschuetzt ist."
    )


#: Hochpräzise Kategorien fürs Rest-PII-Gate (Prüfziffer/starker Anker ->
#: praktisch keine False Positives, auch nicht auf Office-XML/Schema-Text).
_GATE_CATEGORIES: frozenset[str] = frozenset(
    {"IBAN", "CREDITCARD", "UID", "SVNR", "STEUERNR", "FN", "AHV", "TAX_ID", "EMAIL"}
)

_XML_TAG_RE = re.compile(r"<[^>]+>")


def extract_text_for_gate(path: Path) -> str:
    """Extrahiert möglichst VOLLSTÄNDIG den Text einer Ausgabedatei fürs Gate.

    Für Office-Dateien wird der komplette XML-Textinhalt (inkl. Kommentare,
    Kopfzeilen, custom.xml …) gelesen — bewusst gründlicher als der Handler,
    damit auch von ihm übersehene Kanäle geprüft werden.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            pymupdf = _require_pymupdf()
            doc = pymupdf.open(str(path))
            try:
                return "\n".join(p.get_text() for p in doc)
            finally:
                doc.close()
        except Exception:  # noqa: BLE001
            return ""
    if suffix in (".xlsx", ".docx", ".pptx"):
        import zipfile

        parts: list[str] = []
        try:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.endswith(".xml") and "/media/" not in name:
                        with contextlib.suppress(Exception):
                            raw = zf.read(name).decode("utf-8", "replace")
                            parts.append(_XML_TAG_RE.sub(" ", raw))
        except Exception:  # noqa: BLE001
            return ""
        return " ".join(parts)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _unique_target(target: Path) -> Path:
    """Freien Zielnamen finden ('name (2).ext'), statt bestehende zu ueberschreiben."""
    if not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    for i in range(2, 1000):
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
    return target  # extrem unwahrscheinlich


def run(
    base: Path,
    *,
    profile: str = "Standard",
    remove_logos: bool = True,
    ocr_images: bool = True,
    use_llm: bool = True,
    llm_model: str = "mistral:latest",
    poll_seconds: float = 3.0,
) -> int:
    """Startet den Ordner-Watcher (laeuft, bis der Prozess beendet wird)."""
    import os

    # Ohne KI-Modell laufen (regelbasiert + Begriffe) — fuer gesperrte Rechner.
    os.environ.setdefault("PSEUDOKRAT_DISABLE_ML", "1")

    base = base.resolve()
    inbox = base / "INPUT"
    outbox = base / "OUTPUT"
    back_in = base / "ZURUECK_INPUT"
    back_out = base / "ZURUECK_OUTPUT"
    done = base / "Verarbeitet"
    errors = base / "Fehler"
    log_file = base / "watch.log"
    terms_file = base / "Begriffe.txt"

    for folder in (inbox, outbox, back_in, back_out, done, errors):
        folder.mkdir(parents=True, exist_ok=True)

    # Wegweiser-Dateien in leeren Arbeitsordnern (nur einmalig).
    _WEGWEISER = {
        inbox: "_Hier Dateien zum Anonymisieren hineinziehen.txt",
        outbox: "_Hier erscheinen die anonymisierten Ergebnisse.txt",
        back_in: "_Hier die KI-Antwort mit Platzhaltern hineinlegen.txt",
        back_out: "_Hier kommt der Klartext (Originale) zurueck.txt",
    }
    for folder, marker in _WEGWEISER.items():
        with contextlib.suppress(OSError):
            if not any(folder.iterdir()):
                (folder / marker).write_text("", encoding="utf-8")

    # Sitzungs-Trenner ins Log (klarere Historie über mehrere Läufe).
    with contextlib.suppress(OSError):
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n===== Neue Sitzung {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )

    def log(message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        try:
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    print("=" * 64, flush=True)
    print("  Pseudokrat Ordner-Watcher", flush=True)
    print("=" * 64, flush=True)

    # Doppelstart-Lock: verhindert zwei Watcher auf demselben Ordner (die sich
    # sonst gegenseitig die Dateien wegschnappen). Das Lock-Handle bleibt für
    # die Prozesslaufzeit offen und wird beim Beenden automatisch freigegeben.
    lock_path = base / ".pseudokrat_watch.lock"
    lock_handle = lock_path.open("a+")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log(
            "Es läuft bereits ein Pseudokrat-Watcher auf diesem Ordner. "
            "Dieses Fenster kann geschlossen werden."
        )
        lock_handle.close()
        return 0

    log("Starte ... lade Programm (erster Start dauert ueber das Netzlaufwerk etwas).")
    log("Lade Erkennungsmodule ...")

    log("  Lade Anonymizer ...")
    from pseudokrat.anonymizer import Anonymizer

    log("  Lade Deanonymizer ...")
    from pseudokrat.deanonymizer import Deanonymizer

    log("  Lade Recognizer-Bundle ...")
    from pseudokrat.recognizers import recognizers_for_store

    log("  Lade Profilverwaltung ...")
    from pseudokrat.store.profile import ProfileManager
    log("Erkennungsmodule geladen.")

    manager = ProfileManager()
    log(f"Oeffne/erstelle Profil '{profile}' (Simple-Mode, kein Passwort) ...")
    store, audit = manager.open_or_create_simple(profile)

    recognizers = recognizers_for_store(store)
    if ensure_terms_template(terms_file):
        log("Begriffe.txt neu angelegt — eigene Begriffe dort eintragen (optional).")
    terms = load_terms(terms_file)
    if terms:
        recognizers.append(TermRecognizer(terms))
        log(f"{len(terms)} eigene Begriffe aus Begriffe.txt geladen.")

    # Lokaler LLM-Erkenner (Ollama) — erkennt Firmen-/Personen-/Markennamen
    # generisch, laeuft nur auf localhost (kein Cloud-Leck).
    if use_llm:
        from pseudokrat.pii.ollama_detector import OllamaDetector, ollama_available

        if ollama_available():
            recognizers.append(OllamaDetector(model=llm_model, log=log))
            log(f"Lokaler LLM-Erkenner aktiv (Ollama, Modell {llm_model}).")
        else:
            log(
                "Ollama nicht erreichbar — LLM-Erkennung uebersprungen "
                "(nur regelbasiert + Begriffe). Start: 'ollama serve'."
            )

    # Rest-PII-Gate: hochpraezise Erkenner (+ eigene Begriffe) fuer die
    # Nachpruefung der fertigen Ausgabe (Defense-in-Depth, fail-closed).
    gate_recognizers = [
        r for r in recognizers if getattr(r, "category", "") in _GATE_CATEGORIES
    ]
    if terms:
        gate_recognizers.append(TermRecognizer(terms))

    ocr = _OcrEngine(log) if ocr_images else None

    with store:
        anonymizer = Anonymizer(
            store=store,
            recognizers=recognizers,
            detector=None,  # kein KI-Modell -> regelbasierte DACH-Erkennung
            audit_log=audit,
            model_version="disabled",
        )
        deanonymizer = Deanonymizer(store=store, audit_log=audit, model_version="disabled")

        def relocate(path: Path, folder: Path) -> None:
            # Nicht überschreiben (Datenverlust!) — bei Kollision umbenennen.
            shutil.move(str(path), str(_unique_target(folder / path.name)))

        def report_anon(counts: dict[str, int], target: Path) -> None:
            total = sum(counts.values())
            if total == 0:
                log(f"  -> OK, ABER 0 PII erkannt -> {target.name}  ⚠ bitte pruefen!")
                with contextlib.suppress(OSError):
                    (outbox / f"_ACHTUNG {target.stem} - keine PII erkannt.txt").write_text(
                        "In dieser Datei wurde KEINE identifizierende Information "
                        "erkannt.\nBitte pruefen Sie das Ergebnis selbst. Falls doch "
                        "Namen/Marken enthalten sind, tragen Sie diese in Begriffe.txt "
                        "ein und legen die Datei erneut in INPUT.\n",
                        encoding="utf-8",
                    )
            else:
                log(f"  -> OK ({_format_counts(counts)}; Metadaten bereinigt) -> {target.name}")

        def gate_residual(target: Path) -> int:
            """Zählt hochsensible Rest-PII in der fertigen Ausgabe (0 = sauber)."""
            gate_text = extract_text_for_gate(target)
            total = 0
            for recognizer in gate_recognizers:
                with contextlib.suppress(Exception):
                    total += len(recognizer.analyze(gate_text))
            return total

        def process(path: Path, *, reverse: bool) -> None:
            if not _file_is_stable(path):
                return
            is_pdf = path.suffix.lower() == ".pdf"
            counts: dict[str, int] = {}
            if reverse:
                target = _unique_target(back_out / f"{path.stem}.klartext{path.suffix}")
                log(f"Ruckuebersetze: {path.name}")
            else:
                # Dateiname mit-anonymisieren (Klartext-Name -> Platzhalter).
                safe_stem = safe_anonymized_stem(path.stem, anonymizer)
                target = _unique_target(outbox / f"{safe_stem}.anon{path.suffix}")
                log(f"Anonymisiere: {path.name}  (Ausgabe-Name: {target.stem})")
            try:
                if reverse and is_pdf:
                    resolved, missing = deanon_pdf(path, target, deanonymizer)
                    if missing:
                        log(
                            f"  -> OK ({resolved} zurueckgesetzt), ABER {missing} "
                            f"Platzhalter unbekannt (falsches Profil?) -> {target.name}"
                        )
                    else:
                        log(f"  -> OK ({resolved} Platzhalter zurueckgesetzt) -> {target.name}")
                elif reverse:
                    from pseudokrat.formats import handler_for

                    missing_ph: set[str] = set()

                    def _reverse_transform(chunk: str) -> str:
                        result = deanonymizer.deanonymize(chunk)
                        missing_ph.update(result.missing_placeholders)
                        return result.text

                    res = handler_for(path).process(
                        path, target, transform=_reverse_transform
                    )
                    if missing_ph:
                        log(
                            f"  -> OK ({res.segments_processed} Segmente), ABER "
                            f"{len(missing_ph)} Platzhalter unbekannt (falsches Profil?) "
                            f"-> {target.name}"
                        )
                    else:
                        log(f"  -> OK ({res.segments_processed} Segmente) -> {target.name}")
                elif is_pdf:
                    redact_pdf(
                        path, target, anonymizer, store,
                        remove_logos=remove_logos, ocr=ocr, log=log, counts=counts,
                    )
                    report_anon(counts, target)
                else:
                    from pseudokrat.formats import handler_for

                    def _counting_transform(chunk: str) -> str:
                        anon_result = anonymizer.anonymize(chunk)
                        for cat, num in anon_result.entity_counts.items():
                            counts[cat] = counts.get(cat, 0) + num
                        return anon_result.text

                    handler_for(path).process(path, target, transform=_counting_transform)
                    strip_office_metadata(target)  # Dokument-Eigenschaften entfernen
                    report_anon(counts, target)
                # Rest-PII-Gate (Defense-in-Depth): bleibt hochsensible PII in der
                # Ausgabe, NICHT freigeben (fail-closed) — greift bei allen Formaten.
                if not reverse:
                    residual = gate_residual(target)
                    if residual:
                        raise ResidualPIIError(residual)
                relocate(path, done)
            except Exception as exc:  # noqa: BLE001 - im Watcher alles abfangen
                log(f"  -> FEHLER bei {path.name}: {_friendly_error(exc)}")
                # Verständliche Begleit-Datei im Fehler-Ordner.
                with contextlib.suppress(OSError):
                    (errors / f"{path.name}.FEHLER.txt").write_text(
                        "Diese Datei konnte nicht anonymisiert werden.\n\n"
                        + _friendly_error(exc)
                        + f"\n\nTechnisches Detail: {type(exc).__name__}: {exc}\n",
                        encoding="utf-8",
                    )
                # (Teilweise) geschriebene Ausgabe entfernen — nie ein Leck.
                with contextlib.suppress(OSError):
                    if not reverse and target.exists():
                        target.unlink()
                try:
                    relocate(path, errors)
                except OSError as move_exc:
                    log(f"     (konnte Original nicht verschieben: {move_exc})")

        log("BEREIT.")
        log(f"INPUT          (anonymisieren)  : {inbox}")
        log(f"OUTPUT                          : {outbox}")
        log(f"ZURUECK_INPUT  (rueckuebersetzen): {back_in}")
        log(f"ZURUECK_OUTPUT                  : {back_out}")
        print("", flush=True)
        print("  -> Anonymisieren:   Datei in INPUT ziehen.", flush=True)
        print("  -> Rueckuebersetzen: KI-Antwort in ZURUECK_INPUT ziehen.", flush=True)
        print("  -> Beenden: dieses Fenster schliessen oder Strg+C.", flush=True)
        print("", flush=True)

        while True:
            for path in _scan(inbox):
                process(path, reverse=False)
            for path in _scan(back_in):
                process(path, reverse=True)
            time.sleep(poll_seconds)


def _scan(folder: Path) -> list[Path]:
    try:
        return [
            f for f in folder.iterdir()
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXTENSIONS
            and not f.name.startswith("_")  # Wegweiser-/Marker-Dateien überspringen
        ]
    except OSError:
        return []
