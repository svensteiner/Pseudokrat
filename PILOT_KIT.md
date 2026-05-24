# Pseudokrat — Pilot-Kit für DACH-Berufsträger

Dieses Dokument bündelt alles, was für den in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) Punkt 12 geforderten
Pilot-Test mit 5-10 Kanzleien gebraucht wird, **ohne** dass die
Pilot-Teilnehmer den Code selbst lesen müssen.

Es schließt damit nicht die Lücke (echte Pilot-Daten kann nur ein echter
Pilot produzieren), aber es **entkoppelt das Onboarding vom
Entwicklungs-Aufwand**: sobald die Pilotkunden gewonnen sind, ist alles
Material direkt einsatzbereit.

---

## 1. Zielgruppe

Ideales Profil pro Teilnehmer:

* Einzelkanzlei oder kleine Sozietät (≤ 5 Mitarbeiter).
* Technisch interessiert, aber **kein IT-Pro** — wir testen
  Bedienbarkeit, nicht Tooling-Affinität.
* Aktiver KI-Nutzer (ChatGPT, Claude, Gemini) bei Mandanten-bezogenen
  Texten — sonst gibt es nichts zu anonymisieren.
* Bereit, ein **NDA** zu unterschreiben (Pseudokrat-Beobachtungen
  bleiben vertraulich; Mandantenkorrespondenz wird NICHT geteilt).

Anti-Profil (nicht rekrutieren):

* Großkanzleien mit eigener IT-Abteilung — produzieren Feedback, das
  nicht zur DACH-Berufsträger-Persona passt.
* Solo-Berater ohne Mandanten — keine PII-Volumen.

---

## 2. Rekrutierungs-Strategie

| Kanal | Aufwand | Erwartete Conversion |
|---|---|---|
| Persönliches Netzwerk | niedrig | 1-2 Pilot-Plätze |
| LinkedIn-Posts in DACH-Steuer-Gruppen | mittel | 1-2 |
| Kammer-Veranstaltungen (DStV, WPK, Anwaltkammer) | hoch | 2-3 |
| Tax-Tech-Konferenzen (DigiTax, IFA) | hoch | 1-2 |

**Pitch (max. 60 Wörter):**

> Sie schicken Mandanten-Texte zur Vorabprüfung an ChatGPT? Pseudokrat
> anonymisiert die PII vor dem Versand und stellt sie nach der Antwort
> wieder her — alles lokal, kein Cloud-Roundtrip mit Klartext. Wir
> suchen 5 Pilotkanzleien für 6 Wochen. Aufwand: ~ 1 Std/Woche.
> Aufwandsentschädigung: 300 € + lebenslange Pro-Lizenz nach Release.

---

## 3. Pilot-Phasen-Plan (6 Wochen)

### Woche 0 — Onboarding
* Onboarding-Call (30 Min): NDA, Installation, erste Anonymisierung.
* Lieferung: signierter Installer (sobald Cert vorliegt) oder
  Source-Build-Anleitung übergangsweise.
* Profil „Pilot-<Name>" wird beim Setup angelegt.

### Wochen 1-4 — Aktiver Test
* Anonymisierung echter Mandantenkorrespondenz im Tagesgeschäft.
* Wöchentlicher 15-Minuten-Call: was lief, was war seltsam, was fehlt.
* Bug-Reports über privaten Slack/Signal (KEIN öffentliches Issue-
  Tracker, da Bug-Reports manchmal sensible Patterns enthalten können).

### Woche 5 — Stress-Phase
* Strukturierter Test der Tabellen-/PDF-Pipeline mit der eigenen
  Mandantenliste (synthetisch oder aggregiert).
* Audit-Log-Review: stimmt das Hash-Chain-Protokoll mit dem
  wahrgenommenen Aufwand überein?

### Woche 6 — Auswertung
* Abschluss-Call (60 Min).
* Anonymes Feedback-Formular (siehe §6).
* Schriftliches Testimonial-Statement (opt-in).

---

## 4. Installations-Walkthrough für Nicht-Techniker

Diese Anleitung steht parallel als `walkthrough/run.py`-Skript zur
Verfügung (für CLI-versierte Tester) UND als folgende Schritt-für-
Schritt-Liste:

### Windows-Installation (sobald signierter Installer existiert)

1. `Pseudokrat-Setup-0.1.0.exe` herunterladen von der gesicherten
   Pilot-Verteilungs-URL (kein öffentlicher Mirror).
2. Doppelklick → SmartScreen akzeptieren (geht trotz Signatur evtl.
   nach Reputations-Aufbau weg).
3. Installations-Wizard durchklicken (Standard-Pfad
   `C:\Program Files\Pseudokrat\` ist OK).
4. Nach Installation: Start-Menü → „Pseudokrat" → ein
   Erst-Start-Wizard öffnet sich.

### Erst-Start-Wizard

1. **Master-Passwort wählen.** Empfehlung: 12+ Zeichen, gemischt.
   Pseudokrat zeigt KEINEN Passwort-Recovery-Mechanismus — Verlust =
   Profil unrettbar. Wir empfehlen explizit, das Passwort in einen
   bestehenden Kanzlei-Passwort-Manager (1Password / KeePass) zu
   speichern.
2. **Erstes Profil anlegen.** Mandantenkürzel oder „Allgemein". Pro
   Mandant ein eigenes Profil = pro Mandant ein eigener Mapping-Store.
3. **Mandantennummer-Regex (optional).** Falls Ihre Kanzlei
   Mandantennummern nach festem Schema vergibt (z. B. `M-12345`),
   können Sie das hier einmal eintragen → wird ab dann automatisch
   erkannt.
4. **Hotkeys testen.** Standard: `Strg+Shift+A` anonymisieren,
   `Strg+Shift+D` deanonymisieren (Clipboard-basiert).

### macOS-Installation (Phase 2 Pilot)

1. DMG mounten, App nach `/Applications/` ziehen.
2. Rechtsklick → „Öffnen" (Gatekeeper-Sonderdialog).
3. Beim ersten Start: System-Settings → Privacy → Accessibility →
   Pseudokrat aktivieren (nötig für globale Hotkeys).

---

## 5. Test-Szenarien

Wir bitten jeden Tester, mindestens **drei** dieser Szenarien in einer
echten Arbeitswoche zu durchlaufen — gerne mehr.

### Szenario A — E-Mail-Entwurf vor KI-Lektorat

> Sie verfassen eine E-Mail an einen Mandanten, die Rechnungs- und
> Adressdaten enthält. Vor dem Versand möchten Sie ChatGPT bitten,
> den Ton zu glätten.

* `Strg+Shift+A` auf den Mail-Body kopieren → in ChatGPT pasten →
  glätten lassen → Antwort kopieren → `Strg+Shift+D` → Antwort in
  Mail einsetzen.
* **Erfolgs-Kriterien:**
  * Keine erkannten Namen/Adressen/IBANs in der Zwischenablage nach `Strg+Shift+A`.
  * Mail-Body nach `Strg+Shift+D` enthält **alle** Original-Namen
    korrekt.

### Szenario B — Excel-Saldenliste an Steuer-KI

> Sie haben eine Saldenliste mit 200 Mandanten und möchten ChatGPT
> nach Auffälligkeiten fragen.

* CLI: `pseudokrat anonymize --input salden.xlsx --output salden.anon.xlsx --profile Pilot-Hofer`
* Datei in ChatGPT hochladen (oder als CSV einfügen).
* KI-Antwort kopieren → `pseudokrat deanonymize --text "<paste>"`
* **Erfolgs-Kriterien:**
  * Salden-Werte unverändert (oder via `--dp-amounts` rangerhaltend
    permutiert).
  * Pivot-Tabellen funktionieren in der `.anon.xlsx` weiterhin
    (Mandant-Spalte ist konsistent ersetzt).

### Szenario C — PDF-Vertrag

> Ein Mandanten-Vertrag (PDF) soll von der KI grammatikalisch geprüft
> werden.

* `pseudokrat anonymize --input vertrag.pdf --output vertrag.anon.pdf --profile Pilot-Hofer`
* PDF hochladen, Feedback einholen.
* **Erfolgs-Kriterien:**
  * Vertrag bleibt visuell lesbar (Text-Layer ist getauscht, kein OCR-
    Rendering).
  * Anonymisat enthält keine Vertragsparteien, aber alle Paragraphen.

### Szenario D — Wiederkehrende Mandantennummer

> Ihr Kanzlei-Schema vergibt Mandantennummern wie `M-12345`. Diese
> sollen mit-anonymisiert werden.

* Profil-Settings: Mandantennummer-Regex `M-\d{5}`.
* Test-Text: „Bitte zu M-12345 die offenen Posten prüfen."
* **Erfolgs-Kriterien:**
  * `<MANDANT_NR_001>` ersetzt `M-12345`.
  * Konsistenz: wiederholtes Vorkommen → gleicher Platzhalter.

### Szenario E — Falsch erkannte PII korrigieren

> Pseudokrat hat ein Vorkommen markiert, das gar keine PII ist (z. B.
> „AG" am Ende eines Satzes).

* Vorschau-Editor → Klick auf das Highlight → „nicht anonymisieren".
* Folge-Anonymisierung soll DIESES Token nicht mehr markieren (Profil-
  Lernkurve).

---

## 6. Feedback-Formular (Anonym)

Wöchentlich auszufüllen, ~ 5 Min. Bereitgestellt als Google-Form-
Vorlage; Felder unten als Markdown-Spec dokumentiert, damit Form
auch in Tally / Typeform reproduzierbar ist.

```
1. Wie oft haben Sie Pseudokrat diese Woche verwendet?
   [ ] 0× | 1-3× | 4-10× | täglich | mehrmals täglich

2. Welche Szenarien aus §5 haben Sie durchlaufen? (Mehrfachauswahl)
   [ ] A — E-Mail
   [ ] B — Excel
   [ ] C — PDF
   [ ] D — Mandantennummer
   [ ] E — False Positive korrigieren

3. Wie viele Minuten haben Sie diese Woche durch Pseudokrat (a) gespart, (b) verloren?
   gespart: _____  verloren: _____

4. Gab es PII, die NICHT erkannt wurde? (Welche Kategorie? Bitte synthetisches Beispiel, kein Original.)
   [Freitext]

5. Gab es harmlose Texte, die FÄLSCHLICH als PII markiert wurden? (Welche?)
   [Freitext]

6. Wie zufrieden sind Sie mit der Round-Trip-Treue?
   [1 schlecht ----- 5 perfekt]

7. Was würden Sie als nächste Funktion priorisieren?
   [Freitext]

8. Allgemeine Anmerkungen / Bugs / Wünsche
   [Freitext]
```

---

## 7. Bug-Report-Vorlage

Falls Sie einen Bug entdecken — **bitte ohne Mandantendaten**.
Senden Sie an `pilot-feedback@pseudokrat.example` (Signal/PGP-
verschlüsselt; Key-Fingerprint kommt im Onboarding-Call).

```
Was wollten Sie tun? (1-2 Sätze)
Was ist passiert?
Was hätten Sie erwartet?

Pseudokrat-Version: (Hilfe → Über)
OS + Version:
Profil-Größe (Schätzung): wenige / hunderte / tausende Mappings
Modell aktiv (ja/nein):

Synthetisches Reproduktions-Beispiel (KEINE echten Mandantendaten):
```

---

## 8. Erfolgs-Kriterien für „Pilot abgeschlossen"

Wir nennen den Pilot erfolgreich, wenn:

* ≥ 80 % der Tester nach 4 Wochen noch aktiv sind.
* ≤ 1 kritischer False-Negative pro Tester (PII nicht erkannt) in
  Wochen 2-4 — Woche 1 hat höhere Toleranz, da das Profil noch lernt.
* Keine Datenverluste (Profil-Korruption durch Software-Fehler).
* ≥ 4 von 7 Testern erlauben uns ein schriftliches Testimonial-Zitat.

---

## 9. Datenschutz im Pilot selbst

* **Wir bekommen NIEMALS Mandantendaten zu sehen.** Auch keine
  Hashes von Originalen. Audit-Logs bleiben beim Tester.
* Bug-Reports enthalten ausschließlich synthetische Reproduktions-
  Beispiele.
* Feedback-Formulare laufen über DSGVO-konformen Anbieter (Tally
  oder selbst-gehosteter Limesurvey).
* NDA gilt **gegenseitig** — Tester darf über Pseudokrat sprechen
  (Marketing-Win), aber wir veröffentlichen Tester-Namen nur mit
  expliziter Schriftform-Genehmigung.

---

## 10. Kosten-Übersicht (für interne Planung)

| Position | Kosten pro Tester | Gesamt (5 Tester) |
|---|---|---|
| Aufwandsentschädigung | 300 € | 1 500 € |
| Pro-Lizenz Lifetime | 0 € (Marketing) | — |
| Onboarding-Call (30 Min) | 0 € (intern) | — |
| Wöchentliche Status-Calls (6×15 Min) | 0 € (intern) | — |
| Abschluss-Call (60 Min) | 0 € (intern) | — |
| Hardware/Software | 0 € (Tester nutzt eigene) | — |
| **Summe** | | **1 500 €** |

Time-Budget intern: ~ 30 Std pro Pilot (5 Tester × 6 Wochen × 1 Std).

---

## 11. Übergang Pilot → Release

Wenn der Pilot abgeschlossen ist:

1. Findings aus Feedback-Formularen in `PILOT_FINDINGS.md` aufzeichnen.
2. Bugs in CHANGELOG.md / DECISIONS.md verfolgen.
3. Priorisierte Fix-Liste vor 1.0.
4. Testimonials einsammeln und für Marketing-Material aufbereiten.
5. Diese `PILOT_KIT.md` als Vorlage für Pilot 2 (Beta-Welle nach
   1.0-Release) behalten.

---

## Lizenz

Dieses Dokument ist Teil des Pseudokrat-Repositories (MIT) — die
Templates dürfen frei für eigene Pilotphasen verwendet werden.
