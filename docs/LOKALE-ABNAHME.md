# Lokale Abnahme vor produktiver Weitergabe

Die Originaldateien und die Ergebnisse dieser Prüfung bleiben beim Anwender.
Ein erfolgreicher synthetischer Testlauf ersetzt diese Abnahme nicht.

## Repräsentativer Bestand

Mindestens 100 tatsächliche Arbeitsfälle auswählen, einschließlich komplexer
Excel-Blätter, unterschiedlicher Kopfzeilen und Word-Vorlagen. Ein Arbeitsfall
ist das zusammengehörige Paket aus Eingabedateien, nicht eine einzelne Zelle.
Auch blockierte Dateien gehören zum Nenner. Die Auswahl vor dem Test festlegen;
schwierige Fälle nicht nachträglich entfernen.

## Pro Fall lokal festhalten

| Feld | Bedeutung |
| --- | --- |
| Fall-ID | Neutrale lokale Kennung |
| automatisch erledigt | Vorbereitung, geprüfter Export und Rückweg ohne Dateianpassung erfolgreich |
| manuelle Minuten | Prüfzeit separat von notwendigen Korrekturen messen |
| erkannte Leckage | Verbleibende bekannte Namen, Kennungen, Adressen oder versteckte Inhalte |
| numerische Abweichung | Nicht identifizierende Rechenwerte unverändert? |
| Berechnungsabweichung | Original und vorbereitete Kopie lokal in Excel neu berechnen und Resultate vergleichen |
| Rückweg korrekt | Namen, Kennungstypen, Tabellen und benötigte Formatierungen erhalten? |
| Blockiergrund | Nicht unterstützte Dokumentfunktion oder unsichere Verarbeitung |

Die eigene KI kann Kandidaten markieren; die erwarteten Identifikatoren und
fachlichen Berechnungen müssen unabhängig überprüft werden. Eine Übereinstimmung
zweier Modellantworten ist kein Beweis für Vollständigkeit.

## Freigabekriterien

- Automatische Erledigung mindestens 95 Prozent der vorab ausgewählten Fälle.
- Keine bekannte Identifikator-Leckage in freizugebenden Paketen.
- Keine unerklärte Abweichung bei Rechenwerten, Ergebnissen oder Rückwandlung.
- Freigabe der unveränderten Zahlenkombinationen für den vorgesehenen Empfänger.
- Gesicherter Profilschlüssel und erfolgreich getestete Wiederherstellung.

Ein einziger bekannter Datenschutzfehler sperrt den betroffenen Fall unabhängig
von der Gesamtquote. Er wird lokal behoben und als künstlicher Regressionstest
nachgestellt. An Entwickler gehen nur das abstrahierte Fehlerbild und künstliche
Dateien, keine Originaldaten oder Zuordnungen.

## Berichtscode auf dem Spark

Den extern entwickelten Code mit Qwen3-Coder-Next im vertraulichen Arbeitsordner
prüfen: keine externen Dienste, keine festen Beispielwerte, Eingaben nur aus dem
vorgesehenen Ordner und Ausgabe in eine neue Datei. GPT-OSS 120B kann belegte
Auswertungen formulieren. Zahlen werden vom Programm berechnet und mit Quellen
verknüpft; fehlende Fachregeln bleiben ausdrücklich offen. BGE-M3 ist optional
für lokale Suche und nicht für die Berechnung erforderlich.
