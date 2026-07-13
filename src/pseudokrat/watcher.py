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


def load_terms(path: Path) -> list[str]:
    """Liest mandanten-spezifische Begriffe (eine Zeile pro Begriff, ``#`` = Kommentar)."""
    if not path.exists():
        return []
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
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


def redact_pdf(
    src: Path,
    dst: Path,
    anonymizer: Anonymizer,
    store: Any,
    *,
    remove_logos: bool,
    ocr: _OcrEngine | None,
    log: Any,
) -> int:
    """Anonymisiert eine PDF layout-erhaltend. Gibt die Anzahl Treffer zurueck."""
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(src))
    hits = 0
    try:
        # Logos = Bilder, die auf >= 2 Seiten vorkommen (Briefkopf/Logo).
        page_count: dict[int, int] = {}
        for page in doc:
            for xref in {img[0] for img in page.get_images(full=True)}:
                page_count[xref] = page_count.get(xref, 0) + 1
        logo_xrefs = {x for x, c in page_count.items() if c >= 2}

        for page in doc:
            # 0) OCR: Text in (Nicht-Logo-)Bildern finden und im Bild schwaerzen.
            if ocr is not None:
                hits += _ocr_redact_images(page, doc, logo_xrefs, anonymizer, ocr, log)

            # 1) Text-PII ersetzen (Bilder bleiben unangetastet).
            text = page.get_text()
            if text.strip():
                result = anonymizer.anonymize(text)
                pairs: dict[str, str] = {}
                for span in result.spans:
                    pairs[span.text] = store.get_or_create(
                        span.text, span.category
                    ).placeholder
                for original in sorted(pairs, key=len, reverse=True):
                    placeholder = pairs[original]
                    for rect in page.search_for(original):
                        page.add_redact_annot(
                            rect,
                            text=placeholder,
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


def deanon_pdf(src: Path, dst: Path, deanonymizer: Deanonymizer) -> int:
    """Rueckuebersetzung in einer PDF: Platzhalter werden wieder zu Originalen."""
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(src))
    hits = 0
    try:
        for page in doc:
            text = page.get_text()
            for placeholder in set(_PLACEHOLDER_RE.findall(text)):
                original = deanonymizer.deanonymize(placeholder).text
                if original == placeholder:
                    continue
                for rect in page.search_for(placeholder):
                    page.add_redact_annot(
                        rect,
                        text=original,
                        fontname="helv",
                        fontsize=max(4.0, min(11.0, rect.height * 0.8)),
                        fill=(1, 1, 1),
                        text_color=(0, 0, 0),
                        cross_out=False,
                    )
                    hits += 1
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
        doc.save(str(dst), garbage=4, deflate=True)
    finally:
        doc.close()
    return hits


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
            target = folder / path.name
            if target.exists():
                target.unlink()
            shutil.move(str(path), str(target))

        def process(path: Path, *, reverse: bool) -> None:
            if not _file_is_stable(path):
                return
            is_pdf = path.suffix.lower() == ".pdf"
            if reverse:
                target = back_out / f"{path.stem}.klartext{path.suffix}"
                log(f"Ruckuebersetze: {path.name}")
            else:
                # Dateiname mit-anonymisieren (Klartext-Name -> Platzhalter).
                safe_stem = safe_anonymized_stem(path.stem, anonymizer)
                target = outbox / f"{safe_stem}.anon{path.suffix}"
                log(f"Anonymisiere: {path.name}  (Ausgabe-Name: {safe_stem})")
            try:
                if reverse and is_pdf:
                    n = deanon_pdf(path, target, deanonymizer)
                    log(f"  -> OK ({n} Platzhalter zurueckgesetzt) -> {target.name}")
                elif reverse:
                    from pseudokrat.formats import handler_for

                    res = handler_for(path).process(
                        path, target, transform=lambda t: deanonymizer.deanonymize(t).text
                    )
                    log(f"  -> OK ({res.segments_processed} Segmente) -> {target.name}")
                elif is_pdf:
                    n = redact_pdf(
                        path, target, anonymizer, store,
                        remove_logos=remove_logos, ocr=ocr, log=log,
                    )
                    log(f"  -> OK ({n} PII-Stellen ersetzt, Layout+Metadaten bereinigt) -> {target.name}")
                else:
                    from pseudokrat.formats import handler_for

                    res = handler_for(path).process(
                        path, target, transform=lambda t: anonymizer.anonymize(t).text
                    )
                    strip_office_metadata(target)  # Dokument-Eigenschaften entfernen
                    log(f"  -> OK ({res.segments_processed} Segmente, Metadaten bereinigt) -> {target.name}")
                relocate(path, done)
            except Exception as exc:  # noqa: BLE001 - im Watcher alles abfangen
                log(f"  -> FEHLER bei {path.name}: {exc}")
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
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
    except OSError:
        return []
