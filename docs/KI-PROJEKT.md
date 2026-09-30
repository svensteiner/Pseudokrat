# KI-Projekt: Originale lokal halten, Berichtscode entwickeln lassen

Der neue, zusätzliche Modus bereitet XLSX und DOCX gemeinsam vor. Rechenwerte
bleiben unverändert; erkannte Identifikatoren bekommen projektweit gleiche
Platzhalter. Die Zuordnung liegt ausschließlich in `zuordnung.enc`, verschlüsselt
mit dem geöffneten Pseudokrat-Profil. Profile und Schlüssel sichern.

## Ablauf

In der Desktop-Oberfläche steht nach dem Öffnen eines Profils der Reiter
**KI-Projekt** zur Verfügung: Dateien hinzufügen, Vorschau erstellen und öffnen,
lokale Prüfung bestätigen und das ZIP freigeben. Rückwandlung und vertraulicher
Spark-Arbeitsordner sind dort ebenfalls erreichbar. Lange Verarbeitung läuft im
Hintergrund; währenddessen verhindert das Programm ein versehentliches Beenden.

1. Originaldateien lokal vorbereiten. Zusätzliche Namen, Firmen, Projekte und
   andere identifizierende Begriffe in eine lokale UTF-8-Datei schreiben,
   ein Begriff je Zeile. Diese Datei nicht weitergeben.
2. `pseudokrat ki-project --profile mein-profil prepare --input daten.xlsx vorlage.docx --terms Begriffe.txt --output mein-projekt`
3. Alle Dateien unter `mein-projekt/vorschau` lokal prüfen. `pruefung.json` nennt
   Ersatzkennungen und erkannte indirekte Identifikationsmerkmale.
4. Nur wenn keine unzulässigen Identifikatoren verbleiben und die unveränderten
   Zahlen geteilt werden dürfen:
   `pseudokrat ki-project --profile mein-profil publish --project mein-projekt --reviewed --accept-numeric-linkability`
5. Ausschließlich `KI-Paket.zip` an die externe KI geben. Die KI entwickelt damit
   Berichtscode; Originaldateien und Zuordnung bleiben lokal.
6. `pseudokrat ki-project --profile mein-profil local-workspace --project mein-projekt --output originaldaten`
   erzeugt einen **vertraulichen** Arbeitsordner mit echten Daten und einem
   Auftrag für die eigene Spark-KI. Den erhaltenen Berichtscode dort separat
   bereitstellen. Kein automatischer Code-Start und kein Upload.

Eine bearbeitete DOCX oder XLSX mit unveränderten Projekt-Platzhaltern lässt sich
zurückwandeln:

`pseudokrat ki-project --profile mein-profil restore --project mein-projekt --input antwort.docx --output antwort-original.docx`

Fremde oder beschädigte Tokens werden nicht geraten. Eine Rückwandlung kann
keine durch die KI gelöschten Inhalte oder erfundenen Aussagen reparieren.

## Zahlen und Grenzen

- Beträge, Mengen und andere numerische Berechnungswerte bleiben exakt im XML.
- Numerische Identifikatoren in erkannten Identitätsspalten werden zu Tokens.
  Es wird zunächst die erste nichtleere Zeile als Tabellenkopf ausgewertet;
  freie Layouts und anders positionierte Kopfzeilen benötigen lokale Kontrolle.
- Normale Formelausdrücke werden erhalten; Blattreferenzen und erkannte
  Textkriterien werden konsistent ersetzt. Es findet **keine Excel-Neuberechnung**
  statt. Unveränderte Zahlen sind kein Nachweis identischer Formelergebnisse.
- Alle Excel-Blätter bekommen neutrale Namen. Der lokale Original-Arbeitsordner
  verwendet dieselben Namen, sodass Code mit neutralen Referenzen funktioniert.
- Dokumenteigenschaften werden vollständig aus dem Paket entfernt: Ersteller,
  letzter Bearbeiter, Erstellungs-/Änderungsdatum, Titel, Betreff, Firma,
  Manager und benutzerdefinierte Eigenschaften. Zugehörige Paketverweise werden
  ebenfalls entfernt. Die Entfernung hängt nicht von der Namenserkennung ab.
- Excel-Benutzernamen in Freigabeeinstellungen, interne Arbeitsmappen-/Blatt-
  Codenamen und gespeicherte Erzeuger-/Versionsangaben werden entfernt.
  Benutzerdefinierte Ansichten werden wegen weiterer Herkunftsfelder blockiert.
- Vorschaubilder und Custom-XML-Dateninseln werden entfernt. Bilder, Diagramme,
  Pivot-Caches, Kommentare, externe Links,
  Makros und verschiedene komplexe Office-Elemente werden in dieser ersten
  Version ausdrücklich blockiert. Keine stille Freigabe unbekannter Bestandteile.
- Word-Felder/Inhaltssteuerelemente und benutzerdefinierte Excel-Bereichsnamen
  benötigen noch zusätzliche Adapter. Die Dateigröße ist begrenzt.
- Namenserkennung ist nicht vollständig. Die lokale Vorschau ist verpflichtend.
- Die Rückwandlung stellt Inhalte wieder her, nicht entfernte Autorenmetadaten.
  Originaldateien bleiben unverändert. Nur das erzeugte `KI-Paket.zip` freigeben;
  Änderungen an der Vorschau, auch erneutes Speichern in Office, verletzen die
  Hash-Prüfung und verlangen eine neue Vorbereitung.
- Echte Zahlenkombinationen können Personen, Objekte oder Unternehmen erkennbar
  machen. Das Tool behauptet **keine garantierte Anonymität**. Wenn Zuordnung
  weiterhin möglich ist, Paket nicht weitergeben und nur lokal arbeiten.

Der Standardablauf ist offline. GPT-OSS 120B und Qwen3-Coder-Next auf einem
eigenen Spark können im vertraulichen Arbeitsordner die weitere Umsetzung
übernehmen. BGE-M3 kann bei lokaler Suche helfen, ersetzt aber keine Prüfung.

### Optionale Erkennung auf dem eigenen Spark

Im Reiter KI-Projekt die zusätzliche eigene KI ausdrücklich einschalten und
API-Adresse sowie den tatsächlich vom Server angebotenen Modellnamen eintragen.
Die Schnittstelle muss OpenAI-kompatibles `POST /v1/chat/completions` mit einer
JSON-Antwort im Nachrichteninhalt anbieten. GPT-OSS ist für Erkennung und Texte,
Qwen3-Coder-Next für den späteren Berichtscode vorgesehen. BGE-M3 ist ein
Embedding-Modell und gehört nicht in dieses Chat-Modell-Feld.

CLI-Beispiel mit Platzhalter-Adresse im eigenen Netz:

```powershell
pseudokrat ki-project --profile mein-profil prepare --input daten.xlsx vorlage.docx --output mein-projekt --local-endpoint http://192.168.1.50:8000/v1 --local-model SERVER-MODELLNAME --allow-lan
```

Dabei erhält der eigene Server Originaltext. Nur Loopback oder explizit erlaubte
private IP-Adressen werden akzeptiert; Proxys, Weiterleitungen und ein Cloud-
Fallback sind ausgeschaltet. Fehlerhafte Antworten stoppen die Vorbereitung.
Modellvorschläge müssen als exakte Textstellen im Original vorkommen; das Modell
führt weder Code noch Ersetzungen aus. Diese Schnittstelle wurde mit simulierten
Antworten getestet, noch nicht auf dem konkreten Spark des Anwenders.

Formeln, die numerische Identifikatoren verwenden, werden blockiert, weil deren
Ersetzung durch Text die Berechnung verändern könnte. Ebenso werden erkannte
identifizierende zwischengespeicherte Formelergebnisse blockiert: Eine bloße
Ersetzung könnte bei Neuberechnung rückgängig werden. Komplexe Formellogik wird
nicht auf sämtliche möglichen Informationsableitungen geprüft.

Vergleich und Wiederverwendungsentscheidungen: [GitHub-Vergleich](GITHUB-VERGLEICH.md).

## Reifegrad

Aktueller Prüfstand und noch offene Freigabekriterien:
[Produktionsstatus](PRODUKTIONSSTATUS.md).

Validierung am 30.09.2026: Gesamtlauf mit 863 bestandenen Tests; danach ergänzte
Fälle für 65 Word-Abschnitte und sensible Excel-Zahlenformate bestanden in einem
gezielten Lauf mit insgesamt 36 Tests. Ruff und mypy über das gesamte Projekt
bestanden. pytest meldete beim abschließenden Aufräumen einen Windows-Zugriffsfehler
auf seinen temporären Verzeichnisverweis, keine fehlgeschlagenen Testfälle.
Die Tests verwenden künstliche Daten. [Lokaler Abnahmeplan](LOKALE-ABNAHME.md).

Dieser Modus ist eine neue, konservativ begrenzte Erweiterung. Ein erfolgreicher
künstlicher Testbestand belegt nicht, dass 95 % unbekannter echter Dokumente
automatisch bearbeitet werden. Das Produktivitätsziel muss auf einem lokalen,
repräsentativen Korpus separat gemessen werden: mindestens 95 % ohne Nacharbeit,
keine bekannte Identifikator-Leckage in freigegebenen Fällen, unveränderte
Rechenwerte und korrekter Rückweg. Blockierte Fälle zählen als nicht automatisch
erledigt. Der konkrete 60+-Seiten-Berichtscode entsteht erst anhand der geprüften
Vorlage und ihrer fachlichen Feldzuordnungen.
