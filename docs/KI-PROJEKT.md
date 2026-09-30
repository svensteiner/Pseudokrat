# KI-Projekt: Originale lokal halten, Berichtscode entwickeln lassen

Der neue, zusätzliche Modus bereitet XLSX und DOCX gemeinsam vor. Rechenwerte
bleiben unverändert; erkannte Identifikatoren bekommen projektweit gleiche
Platzhalter. Die Zuordnung liegt ausschließlich in `zuordnung.enc`, verschlüsselt
mit dem geöffneten Pseudokrat-Profil. Profile und Schlüssel sichern.

## Ablauf

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
- Standard-Dokumenteigenschaften, Vorschaubilder und Custom-XML-Dateninseln
  werden entfernt. Bilder, Diagramme, Pivot-Caches, Kommentare, externe Links,
  Makros und verschiedene komplexe Office-Elemente werden in dieser ersten
  Version ausdrücklich blockiert. Keine stille Freigabe unbekannter Bestandteile.
- Word-Felder/Inhaltssteuerelemente und benutzerdefinierte Excel-Bereichsnamen
  benötigen noch zusätzliche Adapter. Die Dateigröße ist begrenzt.
- Namenserkennung ist nicht vollständig. Die lokale Vorschau ist verpflichtend.
- Echte Zahlenkombinationen können Personen, Objekte oder Unternehmen erkennbar
  machen. Das Tool behauptet **keine garantierte Anonymität**. Wenn Zuordnung
  weiterhin möglich ist, Paket nicht weitergeben und nur lokal arbeiten.

Der Standardablauf ist offline. GPT-OSS 120B und Qwen3-Coder-Next auf einem
eigenen Spark können im vertraulichen Arbeitsordner die weitere Umsetzung
übernehmen. BGE-M3 kann bei lokaler Suche helfen, ersetzt aber keine Prüfung.

## Reifegrad

Dieser Modus ist eine neue, konservativ begrenzte Erweiterung. Ein erfolgreicher
künstlicher Testbestand belegt nicht, dass 95 % unbekannter echter Dokumente
automatisch bearbeitet werden. Das Produktivitätsziel muss auf einem lokalen,
repräsentativen Korpus separat gemessen werden: mindestens 95 % ohne Nacharbeit,
keine bekannte Identifikator-Leckage in freigegebenen Fällen, unveränderte
Rechenwerte und korrekter Rückweg. Blockierte Fälle zählen als nicht automatisch
erledigt. Der konkrete 60+-Seiten-Berichtscode entsteht erst anhand der geprüften
Vorlage und ihrer fachlichen Feldzuordnungen.
