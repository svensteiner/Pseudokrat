# Lokaler Betrieb auf dem Spark: aktuelle Grenzen und Ablauf

Die Verarbeitung bleibt beim Anwender. Die zentrale Entwicklungs-KI erhält
weder Originaldateien noch lokale Inventare oder Berichtsbelege.

## Vor der Verarbeitung

Die folgenden Befehle setzen eine Linux-Shell, Python ab 3.11 und ein lokales
Checkout voraus. Betriebssystem und Architektur des tatsächlichen Spark sind
hier noch nicht geprüft. Installation und Paketdownloads erfolgen vor der
Verarbeitung vertraulicher Daten, in einem getrennten Einrichtungsschritt.

```bash
python3 --version
uname -m
python3 -m venv .venv
.venv/bin/python -m pip install .
```

Für den Kernablauf sind weder GUI-Abhängigkeiten noch lokale Modelle erforderlich.
Abhängigkeiten für eine Offline-Installation müssen passend zum tatsächlichen
Betriebssystem, zur CPU-Architektur und zur Python-Version vorbereitet werden.
Ein auf Windows zusammengestellter Abhängigkeitenordner ist dafür kein Nachweis.

Vertraulichen Arbeitsbereich außerhalb des Git-Checkouts anlegen, beispielsweise:

```bash
umask 077
mkdir -p "$HOME/pseudokrat-vertraulich"
chmod 700 "$HOME/pseudokrat-vertraulich"
```

Originale und lokale Mapping-Dateien dort ablegen. Vor der Verarbeitung lokal
sicherstellen, dass Berechtigungen, Backups und Netzwerkgrenzen passen. Der
Berichtsgenerator benötigt keine Verbindung zu einer zentralen KI. Ein Verzicht
auf Modellaufrufe ersetzt keine Netzwerkisolation des Betriebssystems.

## Ausführbarer Ablauf

1. [Bestandsaufnahme](SPARK-BESTANDSAUFNAHME.md) lokal erzeugen und prüfen.
2. Unterstützte Word-Platzhalter und Excel-Quellen fachlich zuordnen. Die
   tatsächliche Vorlage nicht still vereinfachen, wenn Funktionen blockiert sind.
3. Mapping gemäß [Berichtsgenerator](LOKALER-BERICHTSGENERATOR.md) erstellen.
   Dynamische Tabellen verwenden Version 2, bedingte Texte Version 3.
4. Einheit, Zeitraum, Zeilenauswahl und Rundung lokal prüfen; erst dann
   `reviewed: true` setzen.
5. Bericht in einem neuen Ausgabeordner erzeugen:

```bash
.venv/bin/python -m pseudokrat.local_report \
  --excel "$HOME/pseudokrat-vertraulich/daten.xlsx" \
  --template "$HOME/pseudokrat-vertraulich/vorlage.docx" \
  --mapping "$HOME/pseudokrat-vertraulich/mapping.json" \
  --output "$HOME/pseudokrat-vertraulich/bericht-001"
```

6. Word-Layout, ausgegebene Kennzahlen und Textaussagen lokal gegen die Originale
   prüfen. `nachweis.json` bleibt ebenso vertraulich wie der Bericht.

## Wichtige Funktionsgrenze auf Linux

Der vorhandene Neuberechnungsadapter benötigt **Windows mit Microsoft Excel**.
`--recalculate-excel` funktioniert auf Linux nicht. Für Formelquellen besteht
damit auf einem Linux-Spark weiterhin eine offene Integrationslücke. Gespeicherte
Excel-Caches werden nicht ersatzweise freigegeben. Originalformeln nicht einfach
durch Werte ersetzen, um die Prüfung zu umgehen.

Für diese Fälle wird noch eine lokal verfügbare Berechnungsengine samt
Kompatibilitätsprüfung benötigt. Ein installierter LibreOffice-Befehl allein
würde keine Gleichheit aller Excel-Ergebnisse beweisen. Die Windows-Live-Tests
sind kein Nachweis für die Spark-Umgebung.

GPT-OSS 120B, Qwen3-Coder-Next und BGE-M3 sind für die deterministische
Berichtserstellung optional. Modellnamen, Endpunkte und die tatsächliche
Erreichbarkeit wurden auf dem Spark noch nicht verifiziert. Die vorhandenen
bedingten Berichtstexte benötigen keinen Modellaufruf; freie Modelltexte mit
anschließender fachlicher Prüfung sind noch nicht integriert.

## Lokale Freigabe

Der [Abnahmeplan](LOKALE-ABNAHME.md) umfasst auch blockierte Arbeitsfälle.
Ein erfolgreicher CLI-Lauf bedeutet nur, dass ein Entwurf erstellt wurde.
Keine Testanzahl ersetzt die Abnahme der konkreten Dateien, des Layouts und
der fachlichen Zuordnung. Rückmeldungen an Entwickler enthalten ausschließlich
geprüfte technische Beschreibungen und unabhängig erzeugte synthetische Beispiele.
