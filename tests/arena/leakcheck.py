"""Leck-Tor und Roundtrip-Prüfung gegen die echte Pseudokrat-Pipeline.

Der Kern der Arena. Für jedes Dokument:

* **Leck-Tor** — kein registriertes Geheimnis darf im anonymisierten
  Text überleben. Verglichen wird in Normalform (siehe
  ``corpus.canonical``), sodass auch ein über Zeilenumbruch/Leerzeichen
  zerrissener Wert als Leck erkannt wird.
* **Roundtrip** — die De-Anonymisierung muss das Originaldokument
  zeichengenau wiederherstellen.

Aus Performancegründen wird **ein** Mapping-Store wiederverwendet und vor
jedem Dokument geleert (``DELETE FROM mappings``). Das gibt pro Dokument
frische Pseudonyme und volle Isolation (kein dokumentübergreifendes
Fuzzy-Merge), spart aber die teure Schlüsselableitung pro Dokument.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pseudokrat.anonymizer import Anonymizer
from pseudokrat.deanonymizer import Deanonymizer
from pseudokrat.recognizers import default_recognizers
from pseudokrat.store.mapping_store import MappingStore
from tests.arena.corpus import ALNUM_CATEGORIES, Document, Secret


@dataclass
class Leak:
    category: str
    value: str
    template: str
    mode: str
    country: str


@dataclass
class DocResult:
    template: str
    mode: str
    country: str
    secret_count: int
    leaks: list[Leak] = field(default_factory=list)
    roundtrip_ok: bool = True
    anonymized: str = ""

    @property
    def clean(self) -> bool:
        return not self.leaks and self.roundtrip_ok


def make_store(db_path: Path) -> MappingStore:
    """Einen Arena-Store anlegen (eine Schlüsselableitung).

    Für den Wegwerf-Test wird der teure Festplatten-Sync abgeschaltet —
    das beschleunigt tausende Dokumente massiv und ist unkritisch, weil
    die DB nach dem Lauf verworfen wird.
    """
    store = MappingStore(db_path, password="arena")
    store.connection.execute("PRAGMA synchronous=OFF")
    store.connection.execute("PRAGMA journal_mode=MEMORY")
    return store


def reset_store(store: MappingStore) -> None:
    """Alle Mappings löschen — nächstes Dokument startet bei <CAT_001>."""
    store.connection.execute("DELETE FROM mappings")
    store.connection.commit()


def _canonical_haystack(category: str, output: str) -> str:
    if category in ALNUM_CATEGORIES:
        return re.sub(r"[^0-9A-Za-z]", "", output).upper()
    return re.sub(r"\s+", " ", output)


def _survives(secret: Secret, output: str) -> bool:
    needle = secret.key
    if not needle:
        return False
    return needle in _canonical_haystack(secret.category, output)


def check_document(doc: Document, store: MappingStore) -> DocResult:
    """Ein Dokument durch die echte Pipeline schicken und prüfen."""
    reset_store(store)
    anon = Anonymizer(store, default_recognizers())
    result = anon.anonymize(doc.text)
    restored = Deanonymizer(store).deanonymize(result.text)

    leaks = [
        Leak(
            category=s.category,
            value=s.value,
            template=doc.template,
            mode=doc.mode,
            country=doc.country,
        )
        for s in doc.secrets
        if _survives(s, result.text)
    ]
    return DocResult(
        template=doc.template,
        mode=doc.mode,
        country=doc.country,
        secret_count=len(doc.secrets),
        leaks=leaks,
        roundtrip_ok=(restored.text == doc.text),
        anonymized=result.text,
    )
