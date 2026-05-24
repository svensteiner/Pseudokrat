# Pseudokrat Word-Add-in

**Status:** Scaffold (Phase 5 des Megaprompts, parallel zu `addins/excel/`).
Compileable Office.js + TypeScript + Webpack, läuft gegen den lokalen
Pseudokrat-HTTP-Server.

Für AppSource-Submission fehlen noch: signiertes Manifest, AppSource-
Validierungs-Lauf (`office-addin-manifest validate manifest.xml`),
Localisation-Bundles (en-US, fr-FR), Privacy Policy, Telemetry-
Opt-Out-Statement. Siehe [Microsoft AppSource Submission Checklist](https://learn.microsoft.com/office/dev/store/submit-to-appsource-via-partner-center).

---

## Voraussetzungen

* Node.js ≥ 18.17
* npm oder pnpm
* Word Desktop (Microsoft 365) oder Word for the web
* Pseudokrat-Python-CLI (im Eltern-Repo)

## Installation

```bash
cd addins/word
npm install
```

## Dev-Server starten

```bash
# Terminal 1: Pseudokrat-Backend
pseudokrat server start --profile "Mandant Hofer" --port 31337

# Terminal 2: Word-Add-in Dev-Server
cd addins/word
npm run dev
```

`webpack-dev-server` lauscht auf `https://localhost:31337/taskpane.html`.
Falls Port 31337 bereits vom Backend belegt ist (gleicher Default-Port),
ändere entweder den Backend-Port oder weiche im Dev-Server auf 31338 aus
und passe `BACKEND_URL` in `src/taskpane.ts` an.

## Sideloading

1. Word starten.
2. **Datei → Optionen → Trust Center → Sicherheits-Center-Einstellungen
   → Vertrauenswürdige Add-In-Kataloge** — Pfad zu `addins/word/`
   eintragen, Häkchen „im Menü anzeigen", Word neu starten.
3. **Add-Ins → Eigene Add-Ins → Freigegebener Ordner → Pseudokrat**.

Die Taskpane öffnet sich am rechten Rand.

## Bedienung

* **Auswahl anonymisieren / deanonymisieren** — operiert auf dem aktuell
  markierten Bereich.
* **Gesamtes Dokument** — `context.document.body.getRange()`, also der
  komplette Body inklusive Tabellen und Listen.
* **Profil-Eingabe** — entscheidet, welches Mandanten-Profil im
  Backend angesprochen wird; der Mapping-Store ist pro Profil isoliert.

## Architektur (kurz)

```
Word UI  ──(Office.js)──>  Taskpane (TypeScript, WebView)
                                │
                                │  HTTPS, Bearer-Token
                                ▼
                          127.0.0.1:31337
                          pseudokrat.server (FastAPI-Stil)
                                │
                                ▼
                         MappingStore + Recognizer
```

Der Bearer-Token wird beim ersten `pseudokrat server start` in der
Konsole ausgegeben. Er muss einmal in den `localStorage` der Taskpane
unter dem Key `pseudokrat:bearer` eingetragen werden (DevTools → Console:
`localStorage.setItem("pseudokrat:bearer", "…")`). Ohne Token antwortet
das Backend mit HTTP 401.

## Bekannte Einschränkungen (Scaffold-Stadium)

* `getSelection().insertText(replacement, Replace)` ersetzt den
  Auswahlbereich als reinen Text — Inline-Formatierung (Fett, Kursiv,
  Hyperlinks) geht in der ersetzten Stelle verloren. Für formatierte
  Anonymisierung wäre eine span-basierte In-Place-Mutation auf
  `Word.Range`-Ebene nötig (siehe `addins/word/src/taskpane.ts`-
  Kommentar). Out-of-scope für Scaffold.
* Track-Changes wird nicht erkannt — die Ersetzung wird als
  „normale" Bearbeitung gespeichert.
* Tabellen-Zellen werden über `body.getRange()` als zusammenhängender
  Text mit Tab-Trennzeichen geliefert; für strukturerhaltende
  Anonymisierung (analog zur XLSX-Pipeline) sollte das Backend künftig
  Bereich-für-Bereich-Aufrufe akzeptieren.

## Tests

Wie bei `addins/excel`: das Office-Addin selbst ist UI-Code mit Browser-
APIs; eine sinnvolle Test-Suite verlangt einen E2E-Setup mit
[Office-Addin-TestServer](https://github.com/OfficeDev/office-addin-test).
Phase-5-Ziel.

## Lizenz

MIT (siehe Repository-Root).
