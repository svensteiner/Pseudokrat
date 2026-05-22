# Pseudokrat Excel-Add-in

**Status:** Scaffold (Phase 5 des Megaprompts). Compileable Office.js +
TypeScript + Webpack, läuft gegen den lokalen Pseudokrat-HTTP-Server.

Für AppSource-Submission fehlen noch: signiertes Manifest, AppSource-
Validierungs-Lauf (`office-addin-manifest validate manifest.xml`),
Localisation-Bundles (en-US, fr-FR), Privacy Policy, Telemetry-
Opt-Out-Statement. Siehe [Microsoft AppSource Submission Checklist](https://learn.microsoft.com/office/dev/store/submit-to-appsource-via-partner-center).

---

## Voraussetzungen

* Node.js ≥ 18.17
* npm oder pnpm
* Excel Desktop (Microsoft 365) oder Excel for the web
* Pseudokrat-Python-CLI (im Eltern-Repo)

## Installation

```bash
cd addins/excel
npm install
```

## Dev-Server starten

```bash
# Terminal 1: Pseudokrat-Backend
pseudokrat server start --profile "Mandant Hofer" --port 31337

# Terminal 2: Webpack-Dev-Server (mit selbst-signiertem HTTPS-Cert)
npx office-addin-dev-certs install
npm run dev
```

Beim ersten Start fragt `office-addin-dev-certs` einmalig nach Admin-
Rechten, um ein Localhost-Root-Cert in den Trust Store zu legen.

## Sideload in Excel

Windows Desktop:

1. Datei → Optionen → Trust Center → Sicherheits-Center-Einstellungen
   → Vertrauenswürdige Add-In-Kataloge.
2. Pfad zu `addins/excel/dist/` (nach `npm run build`) oder zum
   `addins/excel/`-Ordner hinzufügen.
3. Excel neu starten → Add-Ins → Eigene Add-Ins → Freigegebener Ordner
   → „Pseudokrat".

Excel for the web:

1. https://outlook.office.com/owa/admin → Office Add-ins → Hochladen
2. `manifest.xml` hochladen.

## Backend-Auth

Der Webpack-Dev-Server läuft auf `https://127.0.0.1:31337`. Das
Pseudokrat-Backend muss auf derselben Adresse erreichbar sein, sonst
ladet das Add-in nicht.

Der Bearer-Token liegt im Browser-LocalStorage unter dem Key
`pseudokrat:bearer`. Beim ersten Start setzt das Add-in ihn aus der
Datei `%LOCALAPPDATA%\Pseudokrat\server_token.txt`. Anzeigen:

```bash
pseudokrat server token
```

## Build für Produktion

```bash
npm run build
```

Output unter `dist/`. Für AppSource zusätzlich:

```bash
npm run validate    # Manifest gegen die Office-Add-in-Schemas prüfen
```

## Bekannte Lücken

* Keine Word- oder Outlook-Variante (nur Excel). Word + Outlook wären
  einfache Forks dieses Add-ins mit angepasstem Hosts-Element.
* Keine Multi-Locale-Strings (`bt:String`-Resources existieren nur in
  Deutsch).
* Kein Telemetry-Opt-Out-Banner (siehe Pseudokrat-Hauptregel: KEINE
  Telemetry — das Banner ist trotzdem für AppSource verpflichtend).
* HTTPS-Cert ist self-signed; AppSource verlangt für produktive
  Add-ins ein vom Endpunkt aus erreichbares CA-Cert.
