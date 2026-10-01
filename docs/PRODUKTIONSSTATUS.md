# Produktionsstatus KI-Projekt

Stand: 1. Oktober 2026. **Für einen kontrollierten lokalen Pilotbetrieb
getestet; keine allgemeine Produktionsfreigabe und kein Nachweis der 95-%-Quote.**

## Durchgeführte Prüfungen

- Lokaler Word-Generator mit festen Feldern, dynamischen Tabellen, bedingten
  Textbausteinen und vertraulichem Quellennachweis implementiert.
- Microsoft-Excel-16.0-Livetests unter Windows: Neuberechnung, Fehlerzellen,
  versteckte Blätter, getestete Zirkelbezüge und vollständiger Excel-zu-Word-Weg
  bestanden. Timeout nach Öffnen der Arbeitskopie beendet die eigene Instanz
  und entfernt das Arbeitsverzeichnis. Frühe COM-Starthänger sind nicht abgenommen.
- Berichtssuite nach Textregeln: 46 Tests bestanden, ein ausdrücklich optionaler
  Excel-Livetest in diesem Lauf übersprungen. Die separate Excel-Abnahme ist
  oben genannt; dies ist keine Aussage über die gesamten Repository-Tests.
- Ruff über Quellcode und Tests sowie mypy über 79 Quellmodule bestanden.
- Wheel gebaut und in einem temporären Installationsordner geprüft: neue
  Berichtsmodule und PowerShell-Worker sind enthalten und importierbar.
  Das prüft weder eine frische Linux-Installation noch Spark-Abhängigkeiten.

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
   lokal prüfen. Der Generator besteht, unterstützt aber noch nicht sämtliche
   Office-Funktionen wie Bilder, Inhaltssteuerelemente und Word-Felder.
4. Spark-Betriebssystem, Endpunkt und tatsächliche Modellkennungen lokal prüfen.
   Eine Linux-Berechnungsengine ist noch nicht integriert; der Windows-Adapter
   genügt dafür nicht. Freie Modelltexte sind noch nicht angebunden.
5. Wiederherstellung mit gesichertem Profil testen und Zugriffsrechte auf
   vertrauliche Arbeitsordner gemäß lokaler Umgebung prüfen.

Nicht unterstützte Office-Funktionen bleiben blockiert. Namenserkennung und
unveränderte Merkmalskombinationen erlauben keine garantierte Anonymität.
Siehe [Abnahmeplan](LOKALE-ABNAHME.md) und [Funktionsumfang](KI-PROJEKT.md).
Der konkrete Ablauf für den Spark und seine verbleibenden Grenzen stehen in
[Spark-Betrieb](SPARK-BETRIEB.md).
