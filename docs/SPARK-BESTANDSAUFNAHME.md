# Vertrauliche Bestandsaufnahme auf dem Spark

Die zentrale Entwicklungs-KI benötigt keine Originaldateien. Der lokale
Ausführer kann zunächst mit dem folgenden Befehl eine Bestandsaufnahme erzeugen:

```bash
python -m pseudokrat.local_inventory --input /lokal/daten.xlsx /lokal/vorlage.docx --output /lokal/bestandsaufnahme.json
```

Voraussetzung: Python ab 3.11 und eine lokale Installation dieses Repositorys
(`python -m pip install -e .`). Die Installation mit ihren Paketdownloads findet
vor der Verarbeitung vertraulicher Dateien statt. Die Bestandsaufnahme selbst
verwendet keine Netzwerkschnittstelle und benötigt kein Modell.

**Die JSON-Datei ist vertraulich.** Sie enthält Originalpfade, Blattnamen und
möglicherweise Originaltexte aus der ersten nichtleeren Excel-Zeile. Sie bleibt
auf dem Spark. Unter Unix wird sie mit Dateimodus 0600 neu angelegt; unter Windows
gelten zusätzlich die geerbten Zugriffsrechte des Zielordners. Vorhandene Ausgaben
und Originaldateien werden nicht überschrieben.

## Was der lokale Ausführer damit macht

1. Für jedes Excel-Blatt die vorgeschlagene Kopfzeile prüfen. Die erste
   nichtleere Zeile ist lediglich ein Kandidat, keine bestätigte Zuordnung.
2. Formeln ohne Cache feststellen. Vorhandene Caches beweisen keine Aktualität;
   die lokale Neuberechnung und der fachliche Vergleich bleiben erforderlich.
3. Word-Platzhalter der Form `{{ field_name }}` und Tabellen erfassen. Andere
   Platzhalterkonventionen oder feste Textstellen müssen separat zugeordnet
   werden. Die Bestandsaufnahme erkennt diese nicht automatisch als Ziele.
4. Eine lokale Quellen-Ziel-Zuordnung entwerfen und fachlich freigeben lassen.
5. Blockierte Office-Funktionen in einer künstlichen Datei nachstellen, bevor
   ein zusätzlicher Adapter entwickelt wird. Originale nicht zur Fehleranalyse
   an die zentrale KI schicken.

Exitcode 0 bedeutet, dass die Dateien im derzeit unterstützten Umfang untersucht
wurden. Exitcode 20 bedeutet einen Fehler oder mindestens eine blockierte Datei.
Auch bei blockierten Dateien kann ein lokaler Bericht mit Gründen vorliegen.
Keiner der Exitcodes ist eine Freigabe zur Weitergabe von Daten.

## Rückmeldung an den zentralen Baumeister

Nur eine manuell geprüfte technische Beschreibung und künstliche Beispiele
weitergeben. Keine Originalpfade, Überschriften, Werte, Auszüge oder die JSON-Datei.
Zum Beispiel: „Die Vorlage verwendet andere Platzhalter als doppelte geschweifte
Klammern. Hier ist eine vollständig künstliche Vorlage mit derselben Syntax.“

Das Modul ist eine Vorbereitung für den Berichtsgenerator, nicht der Generator
selbst und kein Nachweis vollständiger Anonymität oder Produktionsreife.

Der erste ausführbare Folgeprozess ist im
[lokalen Berichtsgenerator](LOKALER-BERICHTSGENERATOR.md) beschrieben.
