# Lokaler Betrieb auf dem Spark: aktuelle Grenzen und Ablauf

Die Verarbeitung bleibt beim Anwender. Die zentrale Entwicklungs-KI erhält
weder Originaldateien noch lokale Inventare oder Berichtsbelege.

Für die zentrale Entwicklungs-KI gibt es einen kopierbaren
[Baumeister-Prompt](BAUMEISTER-PROMPT.md) mit Arbeitsauftrag, Datenverteilung
und Abnahmekriterien.

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

Vor echten Dateien kann die Installation mit vollständig künstlichen Daten
geprüft werden. Benötigt werden LibreOffice Calc und Writer, `/usr/bin/libreoffice`
sowie `python3-uno` für `/usr/bin/python3`:

```bash
.venv/bin/python -m pseudokrat.spark_smoke --output "$HOME/pseudokrat-selbsttest-001"
```

Dieser Befehl nimmt keine Originaldateien entgegen. Er erzeugt eine künstliche
Excel-Mappe, eine 65-seitige Word-Vorlage und die passende geprüfte Testzuordnung.
Anschließend rechnet Calc neu, der Generator befüllt Text und Tabelle, und Writer
erstellt die PDF-Vorschau. Der Selbsttest prüft die vorgegebenen Sollbeträge,
Textanzahl, Tabellenzeilen, 65 PDF-Seiten, erste/letzte Seitenzahl und unveränderte
Eingaben. Die künstlichen Werte sind ausdrücklich kein Test echter Fachregeln.

Der Ausgabeordner muss neu sein. `smoke.json` enthält die Einzelprüfungen,
Hashes, Architektur und Python-Version. Exitcode 0 bedeutet bestandenen
synthetischen Installationstest; Exitcode 20 einen Fehler. Bei einem Fehler können
synthetische Zwischenstände zur lokalen Diagnose zurückbleiben; für einen neuen
Lauf einen neuen Ordner wählen. Fehlende oder fehlerhafte `smoke.json` ist kein
Erfolg. Auch ein bestandener Lauf setzt `production_approved: false`: Originale,
freie Modelltexte und visuelle Qualität werden dadurch nicht abgenommen.

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

`--recalculate-excel` benötigt **Windows mit Microsoft Excel** und funktioniert
auf Linux nicht. Unter Linux kann stattdessen ausdrücklich
`--recalculate-libreoffice` an den Berichtsbefehl angehängt werden. Gespeicherte
Excel-Caches werden nicht ersatzweise freigegeben. Originalformeln nicht einfach
durch Werte ersetzen, um die Prüfung zu umgehen.

Ein [experimenteller LibreOffice-Adapter](LOKALE-LIBREOFFICE-ENGINE.md) ist
inzwischen mit dem Berichtsbefehl verbunden und unter Ubuntu/WSL getestet.
Auf dem Spark werden weiterhin eine lokal verfügbare Berechnungsengine samt
UNO-Anbindung und Kompatibilitätsprüfung benötigt. Ein installierter LibreOffice-Befehl allein
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
