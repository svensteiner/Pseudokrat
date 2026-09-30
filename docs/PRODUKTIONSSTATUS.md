# Produktionsstatus KI-Projekt

Stand: 30. September 2026. **Für einen kontrollierten lokalen Pilotbetrieb
getestet; keine allgemeine Produktionsfreigabe und kein Nachweis der 95-%-Quote.**

## Durchgeführte Prüfungen

- Gesamtsuite vor der letzten Härtung: 863 Tests bestanden; zusätzliche Fälle
  für große Word-Vorlagen und sensible Excel-Zahlenformate ebenfalls bestanden.
- Nach Härtung des gemeinsamen Excel-Textspeichers: 29 gezielte Tests für
  Office-Projekte, Rückwandlung, CLI und Textspeicher bestanden. Der erweiterte
  Remapping-Test wurde nochmals erfolgreich ausgeführt.
- Ruff und mypy über den gesamten Quellcode bestanden; zusätzlicher Code-Review
  der Textspeicher-Bereinigung ohne offene schwerwiegende Befunde.
- Synthetische Excel-Mappe: 100 Blätter, 11.520 Datenzeilen. Vorbereitung,
  Freigabe und Rückwandlung ausgeführt. 46.080 Identitätszellen ersetzt.
- Vergleich Original/Rückwandlung: keine Abweichungen bei Zellwerten,
  Datentypen oder Zahlenformaten, einschließlich 23.620 Formeln. Numerische
  Rechenwerte und Datumswerte der Datenblätter in der Vorschau unverändert.
- Test der optionalen Spark-Schnittstelle mit simulierten Antworten; kein
  tatsächlicher Aufruf des Spark des Anwenders.

Die große Mappe wurde vor ihrer Verwendung unabhängig zeilenweise mit
Dezimalrechnung kontrolliert. Die Prüfung des Pseudokrat-Rückwegs vergleicht
Formeltexte und Werte; sie ist keine Neuberechnung durch Microsoft Excel und
keine vollständige visuelle Layoutprüfung.

## Behobener Freigabefehler

Nach Ersetzung von Kennungen konnten deren Originaltexte als nicht mehr
verwendete Einträge in `xl/sharedStrings.xml` verbleiben. Die Vorbereitung
entfernt jetzt unbenutzte Einträge und nummeriert verbleibende Zellverweise
korrekt um. Auch beschädigte negative Textindizes werden abgewiesen.
Regressionstests decken Leckage, Referenzverschiebung und Datentyp-Rückweg ab.

## Vor einer Produktionsfreigabe offen

Zusätzliche Metadatenhärtung: Dokumenteigenschaften werden vollständig entfernt,
einschließlich unbekannter Autorenkennungen in Zusatzattributen und
benutzerdefinierten Eigenschaften. Excel-Freigabe-Benutzername, Codenamen und
Programmversionsangaben werden ebenfalls bereinigt; benutzerdefinierte Ansichten
werden blockiert. Ein Lauf mit 31 Projekt-/CLI-/Rückwandlungstests bestand;
anschließend bestanden alle vier Metadatentests einschließlich der ergänzten
Ansichten-Prüfungen. Originale, Rechenwerte und Formeln blieben erhalten.

Die OOXML-Herkunftsfelder sind unter anderem in Microsofts Dokumentation zu
[FileSharing](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.filesharing)
und [FileVersion](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.fileversion)
beschrieben.

1. Repräsentativen echten Bestand ausschließlich beim Anwender prüfen. Die
   95-%-Quote gilt für vollständige Arbeitsfälle; blockierte Fälle mitzählen.
2. Tatsächliche Excel-Neuberechnung von Original und Entwicklungskopie
   vergleichen, besonders bei Textkriterien und numerischen Kennungen.
3. Echte Word-Vorlage einschließlich Formatierung und fachlicher Feldzuordnung
   lokal prüfen. Der individuelle Berichtsgenerator ist eine separate Arbeit.
4. Spark-Endpunkt und tatsächliche Modellkennungen integrieren und lokal testen.
5. Wiederherstellung mit gesichertem Profil testen und Zugriffsrechte auf
   vertrauliche Arbeitsordner gemäß lokaler Umgebung prüfen.

Nicht unterstützte Office-Funktionen bleiben blockiert. Namenserkennung und
unveränderte Merkmalskombinationen erlauben keine garantierte Anonymität.
Siehe [Abnahmeplan](LOKALE-ABNAHME.md) und [Funktionsumfang](KI-PROJEKT.md).
