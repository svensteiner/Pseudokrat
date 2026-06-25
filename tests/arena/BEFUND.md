# Befund: Pseudokrat Testarena — erster belastbarer Lauf

> **Status (PRL Iter-17, 2026-06-25): BEHOBEN.** Beide unten beschriebenen
> Lücken sind geschlossen — die Titel-Liste wurde erweitert und der
> Gazetteer-Pfad gehärtet (siehe D-054). Erneuter Lauf:
> **0 Lecks in 1.500 Dokumenten / 9.750 PII-Werten**
> (`arena_report.md`, „BESTANDEN — 0 Lecks"). Dieser Befund bleibt als
> historische Dokumentation des Erstlaufs erhalten.

**Kurzfassung:** Die Arena ist gebaut und hat beim ersten echten Lauf
(1.500 Dokumente, 9.750 PII-Werte) zwei reale Lücken gefunden, die echte
Mandantennamen in die Cloud durchgelassen hätten. Alles andere ist dicht.

## Was wasserdicht ist

Über 1.500 erzeugte DACH-Dokumente (Lohnabrechnung, Steuerbescheid,
Mandantenbrief, Arztbrief, Anwaltsschriftsatz, Rechnung) in vier
Formatierungs-Härtegraden und drei Ländern (AT/DE/CH):

- **0 Lecks** bei IBAN, SVNR, UID, Steuer-ID, USt-IdNr, AHV, BIC,
  E-Mail, Telefon, Geburtsdatum, Adresse, Firmenname
  (7.500 geprüfte Werte).
- **0 Roundtrip-Fehler** — jede Rückübersetzung stellte das Original
  exakt wieder her.
- Einfache Personennamen (z. B. „Anna Hofer") wurden in **jedem**
  Kontext erkannt.

## Die zwei Funde (Personennamen)

Beide betreffen nur die Personen-Erkennung und hängen am Kontext vor dem
Namen:

1. **Unbekannte Titel.** Steht vor dem Namen ein Titel, den die Engine
   nicht kennt — **„DI"** (Diplomingenieur, in Österreich allgegenwärtig),
   **„BSc"**, **„MBA"**, **„Ing."** —, rutscht der Name durch.
   Bekannte Titel (Dr., Mag., Dipl.-Ing., MMag.) funktionieren.

2. **Adelsprädikat-Namen.** Namen mit **„von" / „zu" / „van der"**
   werden nur nach Anrede oder bekanntem Titel gefangen, **nicht** nach
   einem Rollen-Label wie „An …", „Beklagter: …". Betroffen: 97 von
   2.250 Personen (~4 %).

**Warum das zählt:** Genau diese Fälle („An Herrn DI von Gruber",
„Beklagter: … von …") stehen in echten österreichischen Kanzlei- und
Gerichtsdokumenten. Für die Zielgruppe ist das ein Show-Stopper, der vor
dem Verkauf geschlossen werden sollte.

## Empfohlene Reihenfolge (erst verstehen, dann ausführen, dann kontrollieren)

1. **Fix 1 — Titel-Liste erweitern.** „DI", „DI(FH)", „BSc", „MSc",
   „BA", „MBA", „Ing." in den Titel-Anker des Personen-Recognizers
   aufnehmen (eine eng umrissene Änderung in `recognizers/person.py`).
2. **Fix 2 — Adelsprädikat-Pfad härten.** Die Mehr-Token-Logik für
   von/zu/van der auch im Rollen-Label- und Gazetteer-Pfad greifen
   lassen, nicht nur im Anrede/Titel-Pfad.
3. **Kontrolle.** Arena erneut laufen lassen — Ziel: 0 Lecks im
   realistischen Korpus. Dann ist `arena_report.md` ein belastbarer
   Verkaufs-Nachweis („In 1.500 Dokumenten: 0 Lecks").

## Hinweis

Geprüft wurde die Text-Pipeline. Die Datei-Formate (PDF/DOCX/XLSX) nutzen
dieselbe Engine; ein analoger Datei-Level-Lauf ist der sinnvolle nächste
Ausbau der Arena.

## Bekannte Grenzen (Council-Review, PRL Iter-17) — Backlog

Ein Multi-Perspektiven-Review hat über die zwei behobenen Funde hinaus
folgende **Restlücken** belegt. Sie sind bewusst noch nicht geschlossen
(jede ist ein eng umrissenes Folge-Ticket), aber hier offen dokumentiert,
damit „0 Lecks" nicht mehr verspricht, als es beweist. Alle betreffen
ausschliesslich die heuristische PERSON-Erkennung im recognizers-only-Modus
(ohne geladenes ML-Modell); die deterministischen Recognizer sind dicht.

1. **Zeilenumbruch im Namen.** Bricht ein Name zwischen Vor- und Nachname
   um (`Herr DI Alexander\nHabsburg` — typisch bei PDF-Extraktion), wird nur
   der Vorname erkannt, der Nachname leckt. Fix-Idee: einen einzelnen `\n`
   zwischen Namens-Token im Anker-Pfad zulassen.
2. **Komma-Inversion.** Das Rubrum-Format `Nachname, Vorname`
   (`Gruber, Thomas`) hat keinen Anker und wird nicht erkannt.
3. **Adelstitel als Slot-Fresser.** `Maria Theresia Fürstin zu Schwarzenberg`
   → der Gazetteer verbraucht seine zwei Nachnamen-Slots vor dem Prädikat,
   `Schwarzenberg` leckt. Fix-Idee: nicht-akademische Adelstitel (`Fürstin`,
   `Graf`, `Freiherr` …) in die Titel-/Prädikat-Logik aufnehmen.
4. **Teil-Token-Granularität des Leck-Tors.** Geprüft wird, ob der
   *vollständige* registrierte Wert überlebt. Würde von „Anna Hofer" nur
   „Hofer" durchrutschen, meldet das Tor (zu Unrecht) CLEAN. Härtung:
   zusätzlich Einzel-Token relevanter Kategorien prüfen (FP-Abwägung nötig).
5. **Tabellen-Layout ohne Trennzeichen.** Ein Rollen-Label ohne `:`/Dash
   (reine Spalten-Ausrichtung) plus gazetteer-fremder Vorname ohne Anrede
   ist im recognizers-only-Modus nicht fangbar — Aufgabe des ML-Modells.
6. **Datei-Format-Ebene.** Bisher nur Text-Pipeline (s. o.).
