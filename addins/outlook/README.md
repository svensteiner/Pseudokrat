# Pseudokrat Outlook-Add-in

**Status:** Scaffold (Phase 5 des Megaprompts, parallel zu `addins/excel/`
und `addins/word/`). Compileable Office.js + TypeScript + Webpack, läuft
gegen den lokalen Pseudokrat-HTTP-Server.

Outlook-Add-Ins haben in Office.js zwei Form-Faktoren:

* **ItemEdit (Compose):** Der Nutzer verfasst eine neue Mail / Antwort.
  Das Add-In darf den Body lesen UND ändern (`body.setAsync`). Wir
  nutzen das, um den Entwurf **vor dem Versand an die KI** zu
  anonymisieren.
* **ItemRead:** Der Nutzer liest eine eingegangene Mail. Office.js
  erlaubt hier nur **Lesen** (kein `setAsync`). Wir lesen den
  anonymisierten Klartext einer KI-Antwort und zeigen die
  **deanonymisierte Version in der Taskpane** an (die ursprüngliche
  Mail bleibt unverändert; die Klartext-Version wird nicht in die
  Mailbox geschrieben — Audit-Trail bleibt sauber).

Für AppSource-Submission fehlen noch: signiertes Manifest, AppSource-
Validierungs-Lauf (`office-addin-manifest validate manifest.xml`),
Localisation-Bundles, Privacy Policy, Telemetry-Opt-Out-Statement.

---

## Voraussetzungen

* Node.js ≥ 18.17
* Outlook 2019+ Desktop, Outlook for the web, oder Outlook for Mac
* Pseudokrat-Python-CLI (im Eltern-Repo)

## Installation & Dev-Server

```bash
cd addins/outlook
npm install

# Terminal 1: Pseudokrat-Backend
pseudokrat server start --profile "Mandant Hofer" --port 31337

# Terminal 2: Outlook-Add-in Dev-Server
cd addins/outlook
npm run dev
```

## Sideloading

### Outlook Desktop
1. **Datei → Verwalten von Add-Ins** (oder im Ribbon **Add-Ins
   abrufen**).
2. **Eigene Add-Ins → +-Symbol → Aus Datei hinzufügen** → wählen Sie
   `addins/outlook/manifest.xml`.
3. In jeder Mail-Ansicht (Lesen oder Verfassen) ist nun „Pseudokrat" in
   der Ribbon-Leiste sichtbar.

### Outlook on the web
1. Zahnrad-Icon → **Add-Ins anzeigen** → **Eigene Add-Ins** → **+** →
   **Aus Datei hinzufügen**.
2. Wählen Sie das Manifest und bestätigen Sie.

## Bedienung

* **Beim Verfassen** einer Mail: Ribbon → Pseudokrat → Taskpane öffnet
  sich → „Mail-Entwurf anonymisieren". Der gesamte Body wird durch das
  Anonymisat ersetzt. Sie können das Anonymisat dann ausschneiden und
  in ChatGPT/Claude einfügen.
* **Beim Lesen** einer KI-Antwort, die Sie ins Postfach gemailt
  bekommen haben: Pseudokrat-Taskpane öffnen → „Mail-Inhalt
  deanonymisieren". Der Klartext erscheint **innerhalb der Taskpane**
  — die Mail selbst wird nicht modifiziert.

## Sicherheits-Hinweise (Outlook-spezifisch)

* Outlook-Read-Items dürfen per Office.js-Vertrag nicht modifiziert
  werden — wir halten uns daran, auch wenn das technisch durch einen
  zweiten Hop (Mail → SaveDraft → Replace) umgehbar wäre. Begründung:
  Mandanten-Vertraulichkeit zwischen Originalmail und decrypted view
  ist hier gerade der Punkt; ein „still überschrieben" wäre auditing-
  schwierig.
* `ReadWriteMailbox` ist nötig wegen Compose-Modus; das Manifest fragt
  bewusst nicht nach `ReadWriteMailboxFullAccess` (kein Outlook-REST,
  keine Folder-Iteration).
* Anhänge werden **nicht** angefasst — nur der Body. Eine spätere
  Phase könnte Attachment-Parsing über die Backend-Pipeline
  (XLSX/DOCX/PDF) routen.

## Bekannte Einschränkungen (Scaffold-Stadium)

* HTML-formatierte Mails: wir koerieren mit `Office.CoercionType.Text`.
  Tabellen, eingebettete Bilder und Hyperlinks verlieren ihre Struktur
  beim Anonymisieren. Für strukturerhaltende Anonymisierung müsste das
  Backend einen HTML-Modus bekommen, der DOM-Knoten-Texte einzeln
  routet.
* Signaturen werden mit-anonymisiert. Wer das vermeiden will, soll
  vor Add-In-Nutzung die Signatur per Outlook-Funktion einfügen lassen
  und nur den Mail-Body markieren — entweder über manuelles Cut-Paste
  oder über einen späteren Selektions-Modus.
* Keine Threading-Konsistenz: wenn Sie über 5 Mails hinweg dieselben
  Mandantennamen anonymisieren, müssen Sie dasselbe Profil aktiv haben
  (das ist ohnehin Standard) — aber die Drift zwischen Original-Thread
  und KI-Konversation wird nicht visualisiert.

## Tests

Wie bei den anderen Add-Ins: das Office-Addin selbst ist UI-Code mit
Browser-APIs; eine sinnvolle Test-Suite verlangt einen E2E-Setup mit
[Office-Addin-TestServer](https://github.com/OfficeDev/office-addin-test).
Phase-5-Ziel.

## Lizenz

MIT (siehe Repository-Root).
