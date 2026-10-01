# Lokaler Excel-zu-Word-Entwurf

Dieser Durchlauf liest fest zugeordnete Excel-Quellen und
befüllt Word-Platzhalter ohne Modellaufruf. Der Python-Verarbeitungspfad nutzt
keine Netzwerkverbindung; eine optional gestartete Office-Engine benötigt
separate Netzwerkisolation. Er erzeugt einen
**vertraulichen Entwurf**, keine automatische Produktionsfreigabe.

## Vorlage und geprüfte Zuordnung

Die lokale Word-Vorlage enthält beispielsweise `{{ name }}` im Text und
`{{ total }}` in einer Tabellenzelle. Platzhalter können in mehreren Abschnitten,
Tabellen, Kopf- oder Fußzeilen vorkommen. Durch Word aufgeteilte Textläufe werden
unterstützt. Die aktuelle Syntax erlaubt ASCII-Feldnamen mit Buchstaben,
Unterstrich, Ziffern und Punkten; der erste Buchstabe darf keine Ziffer sein.

Eine lokale `mapping.json` beschreibt Quellen und Ausgabeformat:

```json
{
  "version": 1,
  "reviewed": true,
  "template_sha256": "HIER_DEN_LOKAL_BERECHNETEN_SHA256_DER_VORLAGE_EINTRAGEN",
  "headers": {
    "Daten": {"A1": "Name", "B1": "Betrag EUR"}
  },
  "fields": {
    "name": {
      "sheet": "Daten", "range": "A2", "operation": "cell", "format": "text"
    },
    "total": {
      "sheet": "Daten", "range": "B2:B10", "operation": "sum",
      "format": "decimal", "decimals": 2
    }
  }
}
```

Die Feldnamen müssen genau den in der Vorlage verwendeten Platzhaltern
entsprechen. Bei Version 3 können Felder auch ausschließlich als Eingaben
von Textregeln dienen. `reviewed: true` erst nach lokaler fachlicher Prüfung setzen:
Zeilenumfang, Zeitraum, Einheit/Währung, Filter und Bedeutung jeder Kennzahl.
Das Kennzeichen ist eine Bestätigung des Anwenders, kein unabhängiger Nachweis.

Den Vorlagenhash lokal ermitteln:

```bash
python -c "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('vorlage.docx').read_bytes()).hexdigest())"
```

Nach einer Änderung der Vorlage muss die Zuordnung erneut geprüft und der Hash
aktualisiert werden. Änderungen an erwarteten Excel-Kopfzellen stoppen den Lauf.
Weitere Strukturänderungen außerhalb der geprüften Kopfzellen werden noch nicht
vollständig erkannt; diese bleiben Teil der lokalen fachlichen Prüfung.

## Ausführen

```bash
python -m pseudokrat.local_report --excel daten.xlsx --template vorlage.docx --mapping mapping.json --output neuer-bericht
```

Ergebnis im neuen Ordner:

- `bericht.docx`: befüllter Word-Entwurf.
- `nachweis.json`: Originalwerte, Zellbezüge, Operationen und Hashes der Eingaben
  und der Ausgabe. Diese Datei ist ebenso vertraulich wie der Bericht.

Originale und bestehende Zielordner werden nicht überschrieben. Unter Unix gelten
für neue Dateien 0600 und für den Ergebnisordner 0700. Unter Windows zusätzlich
die Zugriffsrechte des Zielordners prüfen. Konsolenmeldungen enthalten keine
Originalwerte. Exitcode 0 bedeutet Entwurf erstellt, nicht fachlich freigegeben;
Exitcode 20 bedeutet Abbruch ohne fertigen Ergebnisordner.

## Derzeit unterstützte Berechnungen und Grenzen

- `cell`: genau eine Zelle; `sum`: vollständig belegter rechteckiger Zahlenbereich.
- `text`: echte Textzelle einschließlich führender Nullen.
- `decimal`: Dezimaldarstellung mit 0 bis 8 Stellen und Dezimalkomma.
- `integer`: nur tatsächlich ganzzahliger Wert, keine stille Rundung.
- `percent`: Zahlenwert mit 100 multiplizieren und Prozentzeichen anhängen.
- Dezimalrechnung mit expliziter kaufmännischer Rundung, auch bei negativen Werten.
- Leere Quellen, boolesche Werte oder Datumswerte als Beträge werden abgewiesen.
  Unbekannte Zahlenformat-IDs werden nicht als normales Zahlenformat angenommen.
- Formelquellen bleiben standardmäßig gesperrt. Mit `--recalculate-excel`
  berechnet installiertes Microsoft Excel unter Windows eine geprüfte Kopie
  neu. Ein Cache allein reicht nicht. Grenzen und Abnahme:
  [Lokale Excel-Engine](LOKALE-EXCEL-ENGINE.md).
- Unter Linux steht ausdrücklich `--recalculate-libreoffice` zur Verfügung.
  Beide Engine-Optionen sind gegenseitig exklusiv. Es gibt keinen automatischen
  Ersatz durch eine andere Engine. Die Einschränkungen stehen beim
  [LibreOffice-Adapter](LOKALE-LIBREOFFICE-ENGINE.md).
- Tabellen mit fester Zeilenzahl können Feldplatzhalter enthalten. Dynamisch
  wiederholte Tabellenzeilen werden mit Zuordnungsversion 2 unterstützt (unten).
  Fachfilter, freie KI-Texte und weitere Operationen sind noch nicht implementiert.
- Geprüfte Textbausteine mit Zahlenbedingungen werden mit Version 3 unterstützt:
  [Automatische Berichtstexte](BERICHTSTEXTE.md).
- Eingebettete PNG- und JPEG-Bilder bleiben in lokalen DOCX-Berichten erhalten,
  einschließlich Kopfzeilen und dynamischer Tabellenzeilen. Bei wiederholten
  Zeilen werden neue interne Bildkennungen vergeben. Bildbytes und Metadaten
  bleiben unverändert; der Bild-Hash wird im Nachweis gespeichert. Der Bericht
  ist deshalb ausdrücklich kein anonymisiertes Exportpaket.
- Weitere Office-Funktionsgrenzen bleiben bestehen, darunter gesperrte
  VML-/SVG-/EMF-Bilder, Diagramme, Inhaltssteuerelemente und Word-Felder. Diese müssen für die
  reale Vorlage noch gezielt erweitert werden; die Vorlage nicht still ändern.

Geprüft sind ein vollständiger CLI-Durchlauf, Textläufe, Tabellen, Kopfzeilen,
fehlende Zuordnungen und ein synthetischer Bericht mit 65 Abschnitten. Die
tatsächliche Paginierung in Word und fachliche Richtigkeit echter Berichte
bleiben lokal zu prüfen.

Der strikte Parser für exportierbare KI-Projekte unterstützt weiterhin keine
Bilder. Nur `read_local_template` und die lokale Berichtsverarbeitung erhalten
die genannten Bildformate. Externe Bildverknüpfungen, fehlende Bildteile,
unbekannte Zeichnungstypen und doppelte Beziehungskennungen stoppen den Lauf.
Die Prüfung von Bildsignaturen ist keine vollständige Bilddecodierung,
Schadsoftwareprüfung oder Erkennung vertraulicher Bildinhalte. Sichtprüfung
und gegebenenfalls OCR bleiben Teil der lokalen fachlichen Abnahme.

## Dynamische Tabellen mit Version 2

Eine Word-Tabelle enthält eine Musterzeile mit `{{ rows.name }}` und
`{{ rows.amount }}` in den betreffenden Zellen. Der Generator ersetzt diese
Musterzeile durch die zugeordneten Excel-Zeilen. Vorhandene Kopf- und
Abschlusszeilen bleiben stehen; Zell- und Textformatierungen werden kopiert.

```json
{
  "version": 2,
  "reviewed": true,
  "template_sha256": "HIER_DEN_LOKAL_BERECHNETEN_SHA256_DER_VORLAGE_EINTRAGEN",
  "headers": {"Daten": {"A1": "Name", "B1": "Betrag EUR"}},
  "fields": {},
  "tables": {
    "rows": {
      "sheet": "Daten",
      "first_row": 2,
      "last_row": 121,
      "columns": {
        "name": {"column": "A", "format": "text"},
        "amount": {"column": "B", "format": "decimal", "decimals": 2}
      }
    }
  }
}
```

`fields` kann weiterhin globale Felder enthalten, beispielsweise eine
Gesamtsumme außerhalb der Musterzeile. Innerhalb einer Musterzeile sind nur die
Felder der zugehörigen Tabelle zulässig. Jede Tabelle braucht genau eine
vollständige Musterzeile. Tabellen- und Spaltenkennungen bestehen aus maximal
24 ASCII-Buchstaben, Ziffern oder Unterstrichen; die erste Stelle ist keine Ziffer.

Der Bereich ist inklusive beider Zeilengrenzen. Es gibt keine automatische
Erkennung des Datenendes und kein stilles Überspringen leerer Datensätze.
Fehlende Werte stoppen den Lauf. Der Quellennachweis enthält für jede erzeugte
Berichtszeile die ursprünglichen Zellbezüge und Werte.

Aktuelle Grenzen: 50 Tabellen, 1.000 Zeilen pro Tabelle, 50 Spalten pro Tabelle,
10.000 Berichts-/Tabellenfelder insgesamt und 100.000 ausgewertete Zellbezüge.
Überschreitungen werden gemeldet. Vertikale Zellverbünde, verschachtelte Tabellen,
Textmarken sowie Fuß-/Endnotenverweise in der Musterzeile werden gesperrt, weil
deren Verknüpfungen beim Kopieren gesondert behandelt werden müssen.

Ein Test mit 120 Datenzeilen prüft Reihenfolge und Zellnachweise. Weitere Tests
prüfen Nullwerte, negative Beträge, Formatierung und unzulässige Musterzeilen.
Das ist kein Nachweis der späteren Seitenaufteilung in Microsoft Word.
