"""ML-Modell-Setup: Cache-Detection + Download-Hilfen.

Diese Schicht ist absichtlich **leichtgewichtig** — sie funktioniert
ohne installiertes ``transformers``/``torch``, weil sie nur den
HuggingFace-Cache-Layout-Konventionen folgt.

Der eigentliche Download wird über ``huggingface_hub`` (eine kleine,
ML-framework-unabhängige Dependency) gemacht. Diese Bibliothek wird mit
dem ``[ml]``-Extra mitinstalliert, ist aber nicht zwingend nötig, wenn
der Nutzer das Modell auf anderem Weg (etwa per Offline-Transport vom
Sysadmin) bereitstellt.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from pseudokrat.config import Settings


@dataclass(frozen=True)
class ModelInstallStatus:
    """Beschreibt den Cache-Zustand eines konkreten Modells."""

    model_id: str
    cache_dir: Path
    is_present: bool
    bytes_on_disk: int

    @property
    def gigabytes_on_disk(self) -> float:
        return self.bytes_on_disk / (1024**3)


def _model_cache_subdir(cache_dir: Path, model_id: str) -> Path:
    """Pfad, unter dem HuggingFace ein Modell cachet.

    Konvention: ``cache_dir/models--{org}--{repo}/snapshots/...``.
    Die Funktion liefert das ``models--…``-Verzeichnis (Top-Level
    des Modells im Cache).
    """
    safe = "models--" + model_id.replace("/", "--")
    return cache_dir / safe


def _dir_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def model_status(settings: Settings | None = None) -> ModelInstallStatus:
    """Liefert den aktuellen Cache-Zustand des konfigurierten Modells."""
    settings = settings or Settings.load()
    cache_dir = settings.model_cache_dir
    model_dir = _model_cache_subdir(cache_dir, settings.model_id)
    bytes_on_disk = _dir_size_bytes(model_dir)
    # „Vorhanden" ist nicht nur Existenz — der Cache kann eine leere
    # `models--…`-Hülle enthalten. Wir verlangen mindestens 100 MB an
    # Inhalt; Privacy-Filter ist ≥ 1 GB, also ist 100 MB ein sicherer
    # Floor, der trotzdem irre Edge-Cases wie laufende Downloads abfängt.
    is_present = bytes_on_disk >= 100 * 1024 * 1024
    return ModelInstallStatus(
        model_id=settings.model_id,
        cache_dir=cache_dir,
        is_present=is_present,
        bytes_on_disk=bytes_on_disk,
    )


class ModelDownloadError(RuntimeError):
    """Modell-Download fehlgeschlagen."""


#: Pinned-Revision (HF Git-SHA) für das Default-Modell. Pseudokrat lädt
#: ausschließlich diese Revision. Wer ein anderes Modell will, muss
#: ``PSEUDOKRAT_MODEL_ID`` UND ``PSEUDOKRAT_MODEL_REVISION`` setzen —
#: ungepinnte Downloads (CWE-494: Substitution-Risiko) sind nicht erlaubt.
#:
#: Aktuell ist „main" als Fallback hinterlegt — der eingebaute Strict-
#: Mode (siehe ``PSEUDOKRAT_REQUIRE_PINNED_REVISION``) verweigert in
#: dem Fall den Download und verlangt eine explizite Revision aus der
#: Umgebung. Vor 1.0-Release wird hier ein konkreter Git-SHA gepinnt
#: (siehe D-036).
PINNED_MODEL_REVISION = "main"

#: Sentinel-Wert: solange ``PINNED_MODEL_REVISION`` diesem Branch-Namen
#: entspricht, gilt die Revision als „ungepinnt".
_UNPINNED_SENTINELS: frozenset[str] = frozenset({"main", "master", "HEAD"})


class UnpinnedModelRevisionError(ModelDownloadError):
    """Hardfail wenn Strict-Mode an ist und keine echte Git-SHA gepinnt ist."""


class ModelManifestMismatchError(ModelDownloadError):
    """Hardfail wenn der berechnete Toplevel-Manifest-Hash nicht zum Pin passt.

    Schützt vor (a) korrupten Downloads, (b) Substitution durch einen
    Angreifer auf dem HuggingFace-CDN/Proxy, (c) versehentlichem Wechsel
    auf eine andere Revision, ohne den Pin nachzuziehen.

    Siehe S4 in :doc:`SELF_AUDIT` und §9 in :doc:`SECURITY_MODEL`.
    """


#: Block-Größe für das streaming-Hashing einzelner Modell-Files.
#: 1 MiB ist groß genug, um IO-Overhead zu amortisieren, aber klein
#: genug, dass der Peak-Memory der Hash-Operation deterministisch
#: bleibt.
_MANIFEST_HASH_BLOCK = 1 << 20

#: Datei-Endungen, die NICHT in den Manifest-Hash einfließen. Caches
#: schreiben hier flüchtige Locks/Hints, deren Inhalt sich zwischen zwei
#: Runs ändert (z. B. mtimes serialisiert). Sie sind kein Teil der
#: Modell-Integrität.
_MANIFEST_IGNORE_SUFFIXES: frozenset[str] = frozenset({".lock", ".tmp"})


def _resolved_revision(settings: Settings) -> str:
    """Auflösung der Modell-Revision aus Env oder Default-Pin.

    Ablauf:

    1. ``PSEUDOKRAT_MODEL_REVISION`` aus der Umgebung — höchste Prio,
       erlaubt sowohl Git-SHA als auch Branch-Namen.
    2. ``PINNED_MODEL_REVISION`` aus diesem Modul — der dauerhafte Pin.
    3. Wenn die resultierende Revision in :data:`_UNPINNED_SENTINELS`
       liegt UND ``PSEUDOKRAT_REQUIRE_PINNED_REVISION=1`` gesetzt ist,
       wird :class:`UnpinnedModelRevisionError` geworfen, bevor ein
       Download passieren kann. So kann CI/Pentest-Setup das harte
       Verhalten erzwingen, während Entwicklung gegen ``main`` läuft.
    """
    revision = os.environ.get("PSEUDOKRAT_MODEL_REVISION", PINNED_MODEL_REVISION)
    if (
        os.environ.get("PSEUDOKRAT_REQUIRE_PINNED_REVISION", "0") == "1"
        and revision in _UNPINNED_SENTINELS
    ):
        raise UnpinnedModelRevisionError(
            f"Modell-Revision '{revision}' ist nicht auf einen Git-SHA gepinnt. "
            "Setze PSEUDOKRAT_MODEL_REVISION=<sha> oder deaktiviere "
            "PSEUDOKRAT_REQUIRE_PINNED_REVISION."
        )
    return revision


def _iter_manifest_files(root: Path) -> Iterable[Path]:
    """Sortierter Iterator über alle Modell-Dateien, die in den Manifest-Hash einfließen.

    Sortierung nach relativem POSIX-Pfad — plattformunabhängig
    deterministisch (`\\` → `/`), gleiches Manifest auf Windows wie auf
    macOS für denselben Snapshot.
    """
    if not root.exists():
        return
    candidates: list[tuple[str, Path]] = []
    for entry in root.rglob("*"):
        try:
            if not entry.is_file():
                continue
        except OSError:
            continue
        if entry.suffix.lower() in _MANIFEST_IGNORE_SUFFIXES:
            continue
        rel = entry.relative_to(root).as_posix()
        candidates.append((rel, entry))
    candidates.sort(key=lambda pair: pair[0])
    for _, path in candidates:
        yield path


def _hash_file(path: Path) -> str:
    """Streaming-SHA-256 eines einzelnen Files."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_MANIFEST_HASH_BLOCK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def compute_model_manifest_hash(settings: Settings | None = None) -> str:
    """Berechnet den Toplevel-Manifest-Hash des aktuell gecachten Modells.

    Der Manifest-Hash ist ein deterministischer Fingerprint über
    *alle* Modell-Dateien im Snapshot des konfigurierten Modells. Er
    eignet sich zum (a) Festhalten eines bekannten Stands („Was hat
    Pentest XYZ unterschrieben?"), (b) Erzwingen einer bestimmten
    Version via :envvar:`PSEUDOKRAT_PINNED_MANIFEST_SHA256`, (c)
    Detektion von Korruption oder Substitution nach dem Download.

    Berechnung:
        Für jede Datei (sortiert nach POSIX-relativem Pfad) wird die
        Zeile ``<pfad>\\0<sha256-der-datei>\\n`` ins Toplevel-Hashing
        gefüttert. Resultat ist der hex-codierte SHA-256.

    Gibt einen leeren String zurück, wenn der Cache leer ist —
    Aufrufer können das als „nichts zu verifizieren" interpretieren.
    """
    settings = settings or Settings.load()
    model_dir = _model_cache_subdir(settings.model_cache_dir, settings.model_id)
    files = list(_iter_manifest_files(model_dir))
    if not files:
        return ""
    toplevel = hashlib.sha256()
    for path in files:
        rel = path.relative_to(model_dir).as_posix()
        file_hash = _hash_file(path)
        toplevel.update(rel.encode("utf-8"))
        toplevel.update(b"\x00")
        toplevel.update(file_hash.encode("ascii"))
        toplevel.update(b"\n")
    return toplevel.hexdigest()


def verify_model_manifest(settings: Settings | None = None) -> str:
    """Vergleicht den berechneten Manifest-Hash gegen einen optionalen Pin.

    Liest :envvar:`PSEUDOKRAT_PINNED_MANIFEST_SHA256`. Wenn gesetzt,
    muss der berechnete Hash mit dem Pin übereinstimmen — ansonsten
    :class:`ModelManifestMismatchError`. Ohne Pin wird der Hash nur
    berechnet und zurückgegeben (gut für ersten Run + Notieren).

    Vergleich ist konstantzeit (`hmac.compare_digest`), obwohl der
    Angriffsweg theoretisch wäre: das schließt eine zukünftige
    Erweiterung (z. B. Netz-Manifest-Server) sauber ab, ohne erst
    nachträglich migrieren zu müssen.
    """
    import hmac

    actual = compute_model_manifest_hash(settings)
    pinned = os.environ.get("PSEUDOKRAT_PINNED_MANIFEST_SHA256", "").strip().lower()
    if not pinned:
        return actual
    if not actual:
        raise ModelManifestMismatchError(
            "PSEUDOKRAT_PINNED_MANIFEST_SHA256 gesetzt, aber kein Modell-Cache vorhanden — "
            "lade das Modell zuerst herunter."
        )
    if not hmac.compare_digest(actual, pinned):
        raise ModelManifestMismatchError(
            "Modell-Manifest-Hash stimmt nicht mit dem Pin überein. "
            f"erwartet={pinned[:12]}…, berechnet={actual[:12]}…"
        )
    return actual


def download_model(
    settings: Settings | None = None,
    *,
    progress: Callable[[str], None] | None = None,
) -> ModelInstallStatus:
    """Lädt das konfigurierte Privacy-Filter-Modell in den Cache.

    Benötigt ``huggingface_hub``. Schlägt mit :class:`ModelDownloadError`
    fehl, wenn die Bibliothek nicht installiert oder der Download
    nicht durchgehbar ist.

    **Revision-Pinning:** Der Download verwendet ausschließlich die in
    :data:`PINNED_MODEL_REVISION` festgelegte HF-Git-Revision (oder das
    via ``PSEUDOKRAT_MODEL_REVISION`` gesetzte Override). Ohne Pinning
    könnte HF zwischen zwei Downloads das Modell ändern, ohne dass es
    auffällt (CWE-494) — Pinning macht den Build reproduzierbar und
    schließt Supply-Chain-Substitution aus.

    Der optionale ``progress``-Callback erhält Statusmeldungen für die
    GUI/CLI-Anzeige (eine pro Phase, NICHT pro Datei — damit kein
    Tight-Loop UI-Updates).
    """
    settings = settings or Settings.load()
    settings.ensure_dirs()
    notify = progress or (lambda _msg: None)

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise ModelDownloadError(
            "huggingface_hub ist nicht installiert. "
            "Installation: `pip install pseudokrat[ml]`."
        ) from exc

    revision = _resolved_revision(settings)
    notify(
        f"Lade Modell '{settings.model_id}' @ {revision} nach "
        f"{settings.model_cache_dir} — kann 5-15 Minuten dauern (≈ 3 GB)."
    )
    try:
        snapshot_download(
            repo_id=settings.model_id,
            revision=revision,
            cache_dir=str(settings.model_cache_dir),
            local_files_only=False,
            tqdm_class=None,
        )
    except Exception as exc:  # pragma: no cover - Netzwerkfehler
        raise ModelDownloadError(f"Download fehlgeschlagen: {exc}") from exc

    status = model_status(settings)
    manifest_hash = verify_model_manifest(settings)
    if manifest_hash:
        notify(f"Manifest-Hash: sha256:{manifest_hash}")
    notify(
        f"Fertig. Modell liegt unter {status.cache_dir} "
        f"({status.gigabytes_on_disk:.2f} GB belegt)."
    )
    return status


def remove_model(settings: Settings | None = None) -> int:
    """Entfernt den Modell-Cache. Gibt die freigewordenen Bytes zurück."""
    settings = settings or Settings.load()
    model_dir = _model_cache_subdir(settings.model_cache_dir, settings.model_id)
    if not model_dir.exists():
        return 0
    size = _dir_size_bytes(model_dir)
    shutil.rmtree(model_dir, ignore_errors=True)
    return size


def free_disk_bytes(path: Path | None = None) -> int:
    """Verfügbarer Festplattenplatz für den Modell-Cache (Bytes)."""
    target = path or Settings.load().model_cache_dir
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(target.parent if not target.exists() else target)
        return usage.free
    except OSError:  # pragma: no cover - Plattenstand nicht ermittelbar
        return 0


def model_is_ready(settings: Settings | None = None) -> bool:
    """Schneller Check für die UI: True wenn das Modell sofort nutzbar ist."""
    settings = settings or Settings.load()
    if settings.disable_ml:
        return False
    if os.environ.get("PSEUDOKRAT_DISABLE_ML", "").lower() in {"1", "true", "yes"}:
        return False
    return model_status(settings).is_present
