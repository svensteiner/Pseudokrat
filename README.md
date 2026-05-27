# Pseudokrat

**Lokale PII-Anonymisierung für DACH-Berufsträger.**
Damit Ihre Mandanten auch in der Cloud anonym bleiben.

Pseudokrat ist eine 100 % lokal laufende Software, die personenbezogene und
mandantenidentifizierende Daten aus Texten entfernt, **bevor** Sie sie an
ChatGPT, Claude, Gemini oder eine andere Cloud-KI senden. Die KI-Antwort
können Sie anschließend mit einem Klick zurückübersetzen.

Pseudokrat ist gemacht für **Steuerberater, Wirtschaftsprüfer, Anwälte,
Ärzte und HR-Verantwortliche im DACH-Raum** — also für Berufsträger, deren
Verschwiegenheitspflicht (§ 91 WTBG, § 9 RAO, § 54 ÄrzteG, § 203 StGB DE)
die Cloud-Nutzung ohne Anonymisierung de facto verbietet.

> **Aktueller Stand: Phase 1 abgeschlossen + Phase 2/4 in Arbeit.**
> CLI inklusive Datei-Pipelines für TXT, CSV, DOCX, XLSX (Formel-Konsistenz)
> und PDF (Text-Layer-Anonymisierung), ein erstes PySide6-Hauptfenster sowie
> Audit-Log-Export als CSV **und** PDF (reportlab). Office-Add-ins und der
> finale Installer folgen in den späteren Phasen. Siehe Roadmap unten.

---

## Was Pseudokrat anders macht

* **Lokal-only.** Der Klartext verlässt Ihre Maschine nicht. Kein Telemetry,
  kein „phone home", keine Cloud-Abhängigkeit.
* **DACH-Recognizer mit Prüfziffer-Validierung** — IBAN (AT/DE/CH/LI),
  österreichische UID + SVNR, deutsche Steuer-ID + USt-IdNr, Schweizer
  AHV-Nummer, Firmen anhand Rechtsform-Suffix (GmbH, AG, KG, GmbH & Co. KG,
  e.U. …). Alle Erkenner validieren die korrekte Prüfziffer.
* **Reversible Pseudonymisierung** mit verschlüsseltem, master-passwort-
  geschütztem Mapping-Store je Mandantenprofil.
* **Hash-verketteter Audit-Log** für Berufshaftpflicht und Kammerprüfung.
* **KI-agnostisch.** Pseudokrat sendet nichts. Sie kopieren den anonymisierten
  Text in das KI-Tool Ihrer Wahl.

---

## Installation (Phase 1, für technisch interessierte Nutzer)

> **Hinweis:** Ein Klick-und-Los-Installer für Windows ist Teil von Phase 2.
> Bis dahin: drei Befehle.

### Voraussetzungen

* Python 3.11 oder neuer ([python.org/downloads](https://www.python.org/downloads/))
* PowerShell (Windows) oder Terminal (macOS / Linux)

### Schritt-für-Schritt-Anleitung

**1. Pseudokrat-Quellcode laden:**

Wenn Sie git haben:

```powershell
git clone https://github.com/<organisation>/pseudokrat.git
cd pseudokrat
```

Wenn nicht: Laden Sie das ZIP von GitHub herunter und entpacken Sie es.

**2. Python-Umgebung einrichten:**

```powershell
python -m venv .venv
.venv\Scripts\activate         # macOS/Linux: source .venv/bin/activate
```

**3. Pseudokrat installieren:**

```powershell
pip install -e .
```

Das war's. Pseudokrat ist jetzt als CLI-Befehl `pseudokrat` verfügbar.

---

## Erste Schritte (in 60 Sekunden)

### Mandantenprofil anlegen — der einfache Weg (empfohlen)

```powershell
pseudokrat init --profile "Mandant Hofer" --simple
```

**Kein Master-Passwort.** Pseudokrat erzeugt ein 256-Bit-Geheimnis und legt es
im **Windows Credential Manager** (Windows) bzw. **macOS Keychain** (macOS) ab —
gebunden an Ihren OS-Login. Folgebefehle (`anonymize`, `deanonymize`, …)
brauchen kein Passwort, das Profil wird automatisch erkannt:

```powershell
pseudokrat anonymize --profile "Mandant Hofer" --text "Hofer Bau GmbH ..."
```

Sicherheitsmodell: gleiches Niveau wie Edge-Passwort-Speicher oder Outlook-PSTs.
Wer Ihren Windows-Login kontrolliert, kann auch das Mapping lesen. Für 95 %
der Einzelplatz-Nutzer ist das die richtige Wahl.

### Mandantenprofil anlegen — der Compliance-Weg (Kanzlei, Mehrnutzer-PC)

```powershell
pseudokrat init --profile "Mandant Hofer"
```

Pseudokrat fragt zweimal nach einem Master-Passwort. Ohne dieses Passwort ist
das Profil **niemand** zugänglich — auch nicht jemand mit vollem
Windows-Konto-Zugriff. Bewahren Sie das Passwort sicher auf; ein verlorenes
Master-Passwort ist nicht wiederherstellbar.

Per `--password "…"` oder Umgebungsvariable `PSEUDOKRAT_PASSWORD` lässt sich
das Setup auch nicht-interaktiv durchführen (Skripte / CI).

Profile werden unter `%LOCALAPPDATA%\Pseudokrat\profiles\` (Windows) bzw.
`~/.local/share/pseudokrat/profiles/` (macOS / Linux) abgelegt.

### Text anonymisieren

```powershell
pseudokrat anonymize --profile "Mandant Hofer" --password "ihr-master-passwort" `
    --text "Die Hofer Bau GmbH (UID ATU12345675) überweist 1.200 € auf AT611904300234573201."
```

Ausgabe (in der Konsole):

```
Die <COMPANY_001> (UID <UID_001>) überweist 1.200 € auf <IBAN_001>.
[anonymized] 3 Entitäten erkannt: {'COMPANY': 1, 'UID': 1, 'IBAN': 1}
```

Den anonymisierten Text kopieren Sie in ChatGPT, Claude oder ein anderes
Tool und arbeiten dort weiter.

### KI-Antwort zurückübersetzen

```powershell
pseudokrat deanonymize --profile "Mandant Hofer" --password "ihr-master-passwort" `
    --text "Die <COMPANY_001> sollte für <IBAN_001> einen Dauerauftrag einrichten."
```

Ausgabe:

```
Die Hofer Bau GmbH sollte für AT611904300234573201 einen Dauerauftrag einrichten.
```

### Hotkey-Workflow über die Zwischenablage

Workflow A aus dem Produktdesign — kopieren, Hotkey drücken, einfügen — wird
über zwei CLI-Befehle realisiert:

```powershell
pseudokrat clipboard --profile "Mandant Hofer" --password "ihr-master-passwort" anonymize
pseudokrat clipboard --profile "Mandant Hofer" --password "ihr-master-passwort" deanonymize
```

Der erste Befehl liest die aktuelle Zwischenablage, anonymisiert ihren Inhalt
und ersetzt den Inhalt mit dem Anonymisat — bereit zum Einfügen in ChatGPT,
Claude oder Gemini. Der zweite Befehl macht den Vorgang umgekehrt: KI-Antwort
in die Zwischenablage kopieren, Hotkey drücken, Original-Begriffe sind wieder
da.

Damit das in einem Schritt funktioniert, binden Sie die beiden Befehle auf
einen Hotkey Ihrer Wahl:

* **Windows** → Microsoft PowerToys (Keyboard Manager → „Shortcut to launch")
  oder AutoHotkey:
  ```ahk
  ^+a::Run, pseudokrat clipboard --profile "Mandant Hofer" anonymize
  ^+d::Run, pseudokrat clipboard --profile "Mandant Hofer" deanonymize
  ```
* **macOS** → Shortcuts.app, Aktion „Run Shell Script" + Tastenbelegung
  in den Systemeinstellungen.

Pseudokrat selbst registriert bewusst **keinen** globalen Tastatur-Listener
— das würde unter Windows Admin-Rechte und unter macOS eine Accessibility-
Freigabe verlangen. Der CLI-Subbefehl ist die robuste Schnittstelle, die
sich in jedes OS-Hotkey-Werkzeug einbinden lässt.

Erforderliche Zusatz-Abhängigkeit: `pip install pseudokrat[clipboard]`
(installiert `pyperclip`).

### Audit-Log prüfen

```powershell
pseudokrat audit --profile "Mandant Hofer" --password "ihr-master-passwort" verify
pseudokrat audit --profile "Mandant Hofer" --password "ihr-master-passwort" export `
    --output audit-2026-05.csv
```

`verify` prüft, dass die Hash-Kette intakt ist (Manipulationserkennung).
`export` schreibt einen CSV-Bericht für Ihre Berufshaftpflichtversicherung.

### Profile auflisten

```powershell
pseudokrat profiles list
```

### Strukturierte Dateien anonymisieren (Phase 2)

Pseudokrat erkennt das Dateiformat automatisch an der Endung und ruft
die passende Pipeline auf. Original-Dateien bleiben unangetastet — die
anonymisierte Kopie landet standardmäßig neben dem Original mit dem
Infix `.anon` (z. B. `saldenliste.csv` → `saldenliste.anon.csv`).

| Endung                      | Pipeline                                                    |
|-----------------------------|-------------------------------------------------------------|
| `.txt`, `.md`, `.log`       | Volltext                                                    |
| `.csv`, `.tsv`              | Zellenweise (Trennzeichen wird gesnifft)                    |
| `.docx`                     | Paragraphen + Tabellen + Kopf/Fuß (via python-docx)         |
| `.xlsx`                     | Zellen + Formel-String-Literale (via openpyxl)              |
| `.pdf`                      | Text-Layer pro Seite (via pypdf + reportlab)                |

```powershell
pseudokrat anonymize --profile "Mandant Hofer" -i .\saldenliste.xlsx
pseudokrat anonymize --profile "Mandant Hofer" -i .\vertrag.docx -o anonym.docx
pseudokrat anonymize --profile "Mandant Hofer" -i .\brief.pdf
pseudokrat deanonymize --profile "Mandant Hofer" -i .\anonym.docx -o final.docx
```

PDF-Besonderheit: Der Anonymisierer extrahiert den Text-Layer und schreibt
eine neu erzeugte Text-PDF — Layout, Bilder und eingebettete Fonts bleiben
**nicht** erhalten. Das ist bewusst (siehe DECISIONS D-020): die anonymisierte
PDF dient der Cloud-KI als reine Texteingabe, nicht als Druckvorlage.

### Audit-Export

```powershell
pseudokrat audit --profile "Mandant Hofer" verify
pseudokrat audit --profile "Mandant Hofer" export                       # CSV nach stdout
pseudokrat audit --profile "Mandant Hofer" export -o audit.csv          # CSV-Datei
pseudokrat audit --profile "Mandant Hofer" export -f pdf -o audit.pdf   # PDF (reportlab)
```

XLSX-Besonderheit: Zahlenwerte (Saldi, Beträge) werden nicht maskiert;
String-Literale in Formeln wie `=SUMIF(A:A,"Hofer Bau GmbH",B:B)` werden
mit dem Profil-Mapping konsistent ersetzt, sodass Auswertungen nach der
Anonymisierung weiterhin funktionieren.

### Grafische Oberfläche (Beta)

Ein erstes PySide6-Hauptfenster ist verfügbar (optional, aktiviert via
`pip install pseudokrat[gui]`):

```powershell
pseudokrat-gui          # oder: python -m pseudokrat.gui
```

Das Fenster bietet drei Tabs: **Live** (Profil-Öffnen, Vorschau mit
farbigem PII-Highlight pro Kategorie, Live-Anonymisierung und
-Deanonymisierung in einem Schritt), **Datei** (Drag-and-Drop bzw.
Auswahl-Dialog für TXT/CSV/DOCX/XLSX/PDF; jede Datei wird über die
Format-Pipeline anonymisiert oder deanonymisiert und neben dem Original
abgelegt) und **Profile** (Übersicht + Anlage, Hash-Chain-Verifikation).
Der Vorschau-Knopf hebt erkannte PII farbig hervor, ohne das Mapping zu
mutieren — ideal zum Prüfen, BEVOR der Text an die Cloud-KI geht.

Zusätzlich registriert das Hauptfenster ein **System-Tray-Icon** mit
Rechtsklick-Menü gemäß Produktdesign §9: *App öffnen*, *Profil wechseln…*,
*Audit-Log exportieren…* und *Beenden*. Der Audit-Export landet wahlweise
als CSV oder PDF (Dateiendung im Speichern-Dialog bestimmt das Format).

Beim **allerersten Start** (noch kein Profil auf der Platte) führt
Pseudokrat einen drei-Schritte-**Erst-Start-Wizard** durch: Willkommen,
Profilname + Master-Passwort + optionales Mandantennummer-Regex,
Zusammenfassung. Der Wizard ruft dieselbe Anlage-Logik wie `pseudokrat init`
auf (siehe DECISIONS D-026, D-030) — der GUI-Pfad bleibt deckungsgleich
zur CLI. Hotkey-Tests folgen in den nächsten Phase-2-Iterationen.

---

## Anonymisierte Entitäten

Pseudokrat erkennt in Phase 1 folgende PII-Kategorien:

| Platzhalter        | Was wird ersetzt                                            |
|--------------------|-------------------------------------------------------------|
| `<IBAN_xxx>`       | IBANs aus AT, DE, CH, LI (MOD-97-validiert)                 |
| `<UID_xxx>`        | AT-UID (ATU + Prüfziffer) und DE-USt-IdNr.                  |
| `<SVNR_xxx>`       | Österreichische Sozialversicherungsnummer (Mod-11)          |
| `<AHV_xxx>`        | Schweizer AHV-Nummer (756.xxxx.xxxx.xx, EAN-13)             |
| `<TAX_ID_xxx>`     | Deutsche Steuer-Identifikationsnummer (§ 139b AO)           |
| `<COMPANY_xxx>`    | Firmen mit Rechtsform-Suffix (GmbH, AG, KG, e.U. …)         |
| `<EMAIL_xxx>`      | E-Mail-Adressen                                             |
| `<PHONE_xxx>`      | DACH-Telefonnummern (international + national)              |
| `<URL_xxx>`        | URLs (http, https, ftp, `www.`-Adressen)                    |
| `<SECRET_xxx>`     | API-Keys & Tokens (OpenAI, Anthropic, AWS, GitHub, JWT, …)  |
| `<MANDANT_NR_xxx>` | Mandantennummern (konfigurierbar pro Profil)                |

Bei aktiviertem ML-Modul (`pip install pseudokrat[ml]`) zusätzlich:

| Platzhalter      | Quelle: HuggingFace-Privacy-Filter                |
|------------------|----------------------------------------------------|
| `<PERSON_xxx>`   | Personennamen                                      |
| `<ADDRESS_xxx>`  | freitextliche Adressen                             |
| `<DATE_xxx>`     | sensible Datumsangaben (Geburtstag etc.)           |

---

## Konsistenz über mehrere Sitzungen

Innerhalb eines Mandantenprofils erhält **dieselbe Firma** stets denselben
Platzhalter — auch über Wochen und Tausende von Anfragen hinweg. Drei
Schreibweisen derselben Firma werden über Levenshtein-Distanz und
Rechtsform-Vergleich automatisch zusammengeführt:

| Eingabe               | Pseudonym       |
|-----------------------|-----------------|
| `Hofer Bau GmbH`      | `<COMPANY_001>` |
| `Hofer-Bau GmbH`      | `<COMPANY_001>` |
| `hofer bau GmbH`      | `<COMPANY_001>` |
| `Hofer Bau GmbH & Co. KG` | `<COMPANY_002>` (eigene Rechtsperson!) |

---

## Sicherheits-Modell

* Jedes **Mandantenprofil** hat eine eigene Datenbank-Datei.
* Diese Datei ist mit **AES-128-GCM (Fernet)** field-level-verschlüsselt.
* Der Schlüssel wird per **PBKDF2-HMAC-SHA512** mit **256 000 Iterationen** aus
  dem Master-Passwort abgeleitet.
* Das Master-Passwort wird **nie persistent gespeichert**. Vergessen Sie es,
  ist das Mapping verloren — das ist die Garantie, dass niemand anderes die
  Daten lesen kann.
* Der **Audit-Log enthält keinen Originaltext**, nur SHA-256-Hashes der
  *anonymisierten* Inhalte. Damit ist der Log selbst kein PII-Leck.
* Die Hash-Kette macht jede nachträgliche Manipulation erkennbar.

Detailliertere Architektur- und Krypto-Entscheidungen siehe
[DECISIONS.md](DECISIONS.md).

---

## Marktpositionierung (warum es das braucht)

OpenAI hat angekündigt, ihren eigenen Privacy-Filter zu integrieren — ein Indiz,
dass das Problem real ist. Aber:

* Der OpenAI-Filter läuft **in der OpenAI-Cloud**. Der Klartext liegt also
  trotzdem zwei Sekunden auf einem fremden Server.
* Er erkennt **keine DACH-spezifischen PII** (UID, SVNR, AHV, deutsche
  Rechtsformen, Mandantennummern).
* Er bietet **keine reversible Pseudonymisierung** über Sessions hinweg.
* Er liefert **keinen Audit-Log** für Berufshaftpflicht und Kammerprüfung.

Pseudokrat schließt genau diese Lücken — und wird kontinuierlich
DACH-spezifisch erweitert. Siehe [PITCH.md](PITCH.md) für die ausführliche
Marktanalyse.

---

## Roadmap

| Phase | Inhalt                                                       | Status        |
|-------|--------------------------------------------------------------|---------------|
| 1     | CLI, DACH-Recognizer, verschlüsselter Mapping-Store          | ✅ Fertig      |
| 2     | GUI-Shell (PySide6), Datei-Pipeline (TXT/CSV/DOCX/XLSX/PDF)  | 🛠️ Teilweise   |
| 2b    | Hotkey-Workflow + Tray-Icon + Erst-Start-Wizard ✅, Installer ⏳ | 🛠️ Teilweise   |
| 3     | DACH-Vollausbau, Mandantenprofil-UI                          | ⏳ geplant     |
| 4     | PDF-Pipeline + Audit-PDF-Export                              | 🛠️ Teilweise   |
| 4b    | Formel-AST-Tiefenanalyse für XLSX, Differential-Privacy      | ⏳ geplant     |
| 5     | Office-Add-ins (Excel, Word, Outlook)                        | ⏳ geplant     |
| 6     | Distribution: DATEV-Marketplace, Kammer-Kooperationen        | ⏳ geplant     |

---

## Entwicklung

```powershell
pip install -e ".[dev]"
ruff check src tests
ruff format src tests
mypy src/pseudokrat
pytest --cov -m "not ml and not slow"
```

Mindestens **80 % Test-Coverage** ist die CI-Hürde — aktuell **≥ 90 %**.
ML-abhängige Tests sind als `@pytest.mark.ml` markiert und laufen nicht in CI.
Headless-GUI-Tests laufen mit `QT_QPA_PLATFORM=offscreen`.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
