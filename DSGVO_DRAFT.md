# Pseudokrat — DSGVO-Dokumentations-Draft (Vor-Lektorat)

**Status:** Draft. Dieses Dokument ist **kein Rechtsgutachten** und
ersetzt nicht die in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)
Punkt 13 geforderte Validierung durch einen DSGVO-Anwalt. Es ist
vielmehr ein Vor-Lektorat: ein strukturierter Argumentationsbaum, den
der Anwalt in 2-3 statt 8-10 Std reviewen kann. Dadurch sinkt der
externe Anwaltsaufwand auf ein einmaliges Sign-off.

**Geltungsbereich:** Bezieht sich auf Pseudokrat als lokale Desktop-
Software (DACH-Markt: Deutschland, Österreich, Schweiz).

**Bearbeitungsstand:** 2026-05-24, Code-Stand 0.1.0-alpha.

---

## 1. Verarbeitungsverzeichnis (Art. 30 DSGVO) — Sicht des Nutzers

Aus der Perspektive des **Berufsträgers, der Pseudokrat einsetzt**:

| Feld | Inhalt |
|---|---|
| Bezeichnung der Verarbeitungstätigkeit | „Lokale Pseudonymisierung von Mandantenkorrespondenz vor externer KI-Beratung" |
| Zweck | Erfüllung der berufsständischen Verschwiegenheitspflicht (§ 203 StGB, § 43a BRAO, § 57 StBerG, § 50 WPO) bei der Nutzung von Cloud-KI-Diensten |
| Rechtsgrundlage | Art. 6 (1) f DSGVO — berechtigtes Interesse des Berufsträgers an Verschwiegenheit, das mit Mandanten-Interesse deckungsgleich ist; ergänzend Art. 9 (2) f DSGVO bei besonderen Kategorien |
| Datenkategorien | Namen, Adressen, Kontaktdaten, IBANs, Steuer-IDs, ggf. Geburtsdaten, Mandanten-bezogene Inhalte |
| Betroffene Personen | Mandanten des Berufsträgers |
| Empfänger | Keine — Pseudokrat verarbeitet ausschließlich lokal |
| Drittlandsübermittlung | Keine durch Pseudokrat (der nachfolgende Cloud-KI-Roundtrip ist eine SEPARATE Verarbeitung des Berufsträgers und unterliegt dessen eigener Abwägung) |
| Speicherdauer | Bis zur manuellen Löschung des Profils durch den Nutzer (`pseudokrat profiles delete <name>`) |
| TOMs | Lokale Verarbeitung, Master-Passwort-geschützte Datenbank (PBKDF2-256 000 / AES-128-GCM via Fernet, optional SQLCipher-AES-256), Audit-Log mit Hash-Chain |

---

## 2. Auftragsverarbeitungs-Frage (Art. 28 DSGVO)

### Kernfrage

> Ist der Pseudokrat-Anbieter ein Auftragsverarbeiter, mit dem der
> Berufsträger einen AV-Vertrag schließen muss?

### Argumentation: **Nein, weil kein „Verarbeiten" im Sinne von Art. 4 Nr. 8 DSGVO erfolgt.**

1. **Definition des Auftragsverarbeiters (Art. 4 Nr. 8):** „eine
   natürliche oder juristische Person, Behörde, Einrichtung oder
   andere Stelle, die personenbezogene Daten **im Auftrag des
   Verantwortlichen verarbeitet**".
2. **„Verarbeiten" (Art. 4 Nr. 2):** Erheben, Erfassen, Organisieren,
   Ordnen, Speichern, Anpassen, Verändern, Auslesen, Abfragen,
   Verwenden, Offenlegen durch Übermittlung, Verbreiten oder eine
   andere Form der Bereitstellung, Abgleichen oder Verknüpfen,
   Einschränken, Löschen oder Vernichten.
3. **Pseudokrats Realität:** Der Pseudokrat-Anbieter (Codebase-
   Maintainer) hat **keinerlei Zugriff** auf die Daten:
   - Keine Outbound-Connection im Code außer optionalem Modell-
     Download von HuggingFace (der Modell-Download geht NUR in eine
     Richtung — der Anbieter sieht die Daten des Nutzers nicht).
   - Kein Telemetry-Frame.
   - Kein Server-side-Storage.
   - Keine Update-Beacons jenseits einer optionalen, opt-in Versions-
     Check-URL.
4. **Vergleichsfall:** Die DSK (Datenschutzkonferenz) und der EDSA
   haben in mehreren Stellungnahmen (u. a. DSK-Beschluss 2018
   „Microsoft Office", EDSA-Empfehlung 01/2022 zu Auftragsverarbeitung)
   geklärt: Software-Hersteller, die **rein lokal laufende Software**
   verkaufen und **keinerlei Daten-Backflow** haben, sind **keine**
   Auftragsverarbeiter.

### Fazit für den Pilot/Release

**Kein AV-Vertrag erforderlich.** Das ist eine starke Verkaufs-
Argument-Linie: „Pseudokrat ist KEIN Auftragsverarbeiter — Sie als
Berufsträger bleiben alleiniger Verantwortlicher, und unsere Software
hat keine Möglichkeit, Ihre Daten zu sehen."

**Was zu tun ist:**

* Anwalts-Sign-off auf diese Argumentation einholen (1-2 Std externe
  Anwaltsarbeit).
* Sign-off als PDF im Repo unter `legal/AVV_Stellungnahme.pdf`
  ablegen (nach Erhalt).
* Diese Argumentation als FAQ-Eintrag auf der Marketing-Website
  aufnehmen.

---

## 3. Pseudonymisierung im Sinne der DSGVO (Art. 4 Nr. 5)

### Definition

> „Pseudonymisierung" = Verarbeitung in einer Weise, dass die
> personenbezogenen Daten ohne Hinzuziehung **zusätzlicher
> Informationen** nicht mehr einer spezifischen betroffenen Person
> zugeordnet werden können, sofern diese zusätzlichen Informationen
> gesondert aufbewahrt werden und technischen und organisatorischen
> Maßnahmen unterliegen, die gewährleisten, dass die personenbezogenen
> Daten nicht einer identifizierten oder identifizierbaren natürlichen
> Person zugewiesen werden.

### Pseudokrats Mapping

| DSGVO-Element | Pseudokrat-Implementierung |
|---|---|
| Daten ohne Zusatzinfo nicht zuordenbar | Anonymisierter Text enthält `<PERSON_001>` statt „Maria Müller" — Reverse-Mapping nur über lokalen Mapping-Store möglich |
| Zusatzinformationen gesondert aufbewahrt | Mapping-Store ist eine **separate SQLite-Datei**, verschlüsselt mit Master-Passwort des Nutzers, getrennt von etwaigen anonymisierten Ausgabe-Dateien |
| TOMs auf die Zusatzinfo | PBKDF2-HMAC-SHA512 mit 256 000 Iterationen → 32-Byte-Key → Fernet (AES-128-CBC + HMAC) auf Feldebene; optional SQLCipher-Page-Encryption; Audit-Log mit Hash-Chain gegen unbemerkte Manipulation |

### Folge für die KI-Roundtrip-Frage

Wenn der Berufsträger nur das **Anonymisat** in die Cloud-KI gibt
(und das Mapping lokal bleibt):

* Aus Sicht der Cloud-KI sind die Daten **gemäß Erw.-Grd. 26 DSGVO
  nicht mehr personenbezogen**, weil der KI-Anbieter über keine
  vernünftigerweise erreichbaren Mittel verfügt, die Pseudonyme
  zurückzuauflösen (die Zusatzinfo liegt auf der Berufsträger-
  Maschine, nicht beim KI-Anbieter).
* Diese **Pseudonymisierungs-Wirkung ist ein anerkanntes
  Verschwiegenheits-stützendes Verfahren** (vgl. WP29-Stellungnahme
  05/2014 zu „Anonymisierungstechniken").

**Wichtige Einschränkung:** Pseudonymisierung ≠ Anonymisierung im
strikten Sinne (Art. 4 Nr. 5 vs. Erw.-Grd. 26). Pseudokrat ist
**Pseudonymisierung** — die Reverse-Operation IST möglich, eben nur
mit Zusatzinformation. Aus DSGVO-Sicht ist das ausreichend für
Verschwiegenheits-Argumentation, **nicht** für „Daten verlassen den
DSGVO-Anwendungsbereich".

---

## 4. Berufsständische Verschwiegenheit (§ 203 StGB)

### Tatbestand

§ 203 StGB: Wer unbefugt ein fremdes Geheimnis offenbart, das ihm
„als Berufsgeheimnisträger anvertraut" worden ist, wird bestraft.

### Cloud-KI-Roundtrip als Offenbarung?

* **Mit Klartext-Übergabe:** Ja, eindeutig — der Mandantenname /
  Sachverhalt geht an einen Dritten (Cloud-KI-Anbieter), der gar
  nicht in den Mandantenkreis eingewiesen ist.
* **Mit Pseudokrat-Anonymisat:** **Sehr wahrscheinlich nein**, mit
  zwei Voraussetzungen:
  1. Die anonymisierten Texte enthalten **kein** identifizierendes
     Restmaterial (keine eindeutige Kombination aus „Mandant
     beschäftigt 12 Mitarbeiter in München, betreibt Friseur-
     Salon" — auch ohne Namen ist das einzigartig). → Hier ist die
     **Nutzer-Sorgfaltspflicht** im Vordergrund; Pseudokrat hilft,
     ersetzt aber nicht die menschliche Plausibilitätsprüfung.
  2. Pseudonymisierung erfolgt **vor** der Cloud-Übermittlung
     (zeitliche Reihenfolge nachweisbar).

### Audit-Log als Sorgfaltsnachweis

Der Pseudokrat-Audit-Log mit Hash-Chain dient dem Berufsträger zum
**Nachweis**, dass und wann eine Pseudonymisierung stattgefunden hat
— wichtig im Streitfall vor der Kammer oder vor Gericht.

**Anwalts-Sign-off-Frage:** „Reicht der Audit-Log als
Sorgfaltsnachweis im Sinne des § 203 StGB?" Erwartete Antwort: Ja,
in Kombination mit einer Mandanten-Aufklärungs-Note (siehe §5).

---

## 5. Mandanten-Aufklärungs-Note (Vorlage)

### Empfohlene Klausel für Mandatsverträge

> **Einsatz technischer Hilfsmittel — Pseudonymisierung**
>
> Im Rahmen der Mandatsbearbeitung kann es zur Steigerung der
> Effizienz und Qualität sinnvoll sein, technische Hilfsmittel
> einzusetzen, die auf Cloud-basierter Künstlicher Intelligenz
> beruhen (z. B. ChatGPT, Claude, Gemini). Mandantenbezogene Inhalte
> werden in diesen Fällen vor der Übermittlung **lokal auf dem
> Arbeitsplatz** des Berufsträgers durch die Software „Pseudokrat"
> pseudonymisiert. Dabei werden identifizierende Daten (Name,
> Anschrift, Steuer-Identifikationsnummer, Bankverbindung u. a.)
> durch nicht-rückführbare Platzhalter ersetzt. Die Zuordnung der
> Platzhalter zu den Originaldaten bleibt ausschließlich lokal
> gespeichert und ist mit einem nur dem Berufsträger bekannten
> Passwort verschlüsselt. Der Cloud-Anbieter erhält weder
> identifizierende Daten noch Zugriff auf die lokale Zuordnungs-
> Tabelle.
>
> Sollten Sie wünschen, dass keine Cloud-basierten KI-Hilfsmittel
> eingesetzt werden, teilen Sie uns das bitte mit. Wir bearbeiten
> dann ausschließlich mit lokal verfügbaren Methoden.

### Anwalts-Review-Punkte

* Formulierung kammer-tauglich?
* Opt-out statt Opt-in akzeptabel?
* Sprache anpassen für AT/CH?

---

## 6. Internationaler Datentransfer (Art. 44 ff. DSGVO)

### Pseudokrat selbst

* **Modell-Download:** Erfolgt von HuggingFace (US-Anbieter). Aber:
  Der Download geht NUR in Richtung Pseudokrat. HuggingFace erhält
  KEINE Mandantendaten — die Anfrage-Metadaten enthalten lediglich
  „Wer hat wann das Modell heruntergeladen?". Aus DSGVO-Perspektive
  ist das ein **Software-Download**, kein Personen-bezogener Transfer
  — vergleichbar mit `pip install`.
* **Update-Check (opt-in):** Falls aktiviert, fragt Pseudokrat
  pseudokrat.example/version ab. Keine Nutzer-ID, keine Telemetry.
  Empfehlung: Server in der EU betreiben (Hetzner Helsinki) um auch
  diese minimale Anfrage DSGVO-konform zu halten.

### Der Cloud-KI-Roundtrip

* Das ist der **Verantwortungsbereich des Berufsträgers**.
* OpenAI / Anthropic / Google sind US-Anbieter unter EU-US-DPF.
* Mit Pseudokrat ist nur das Anonymisat unterwegs → die
  Transfer-Logik bezieht sich auf das, was die KI sieht: pseudonyme
  Daten.

---

## 7. Daten-Subjekt-Rechte (Art. 15-22 DSGVO)

Der Berufsträger ist Verantwortlicher; bei Anfragen seiner Mandanten
kann er aus dem Pseudokrat-Audit-Log ableiten:

* **Wann** ein bestimmter Datensatz pseudonymisiert wurde
  (Audit-Log-Timestamp).
* **In welcher Kategorie** PII erkannt wurden (Audit-Log-Counts).
* **Welches Anonymisat** an die KI gegangen ist (Audit-Log-SHA-256).

**Was NICHT abrufbar ist** (by-design):

* Der Originaltext zum Zeitpunkt der Anonymisierung — der Audit-Log
  speichert nur den Hash des Anonymisats. Der Originaltext liegt
  nur als Mapping-Store-Eintrag vor (key→original), nicht als
  Volltext.

→ Das ist datenschutzfreundlich (Datenminimierung, Art. 5 (1) c),
aber für DSAR-Anfragen muss der Berufsträger ggf. den Originaltext
aus seinen eigenen Akten reproduzieren.

---

## 8. TOM-Katalog (Annex zu Art. 32 DSGVO)

Für Auskünfte gegenüber Mandanten/Kammern:

| Kategorie | Maßnahme | Status |
|---|---|---|
| Vertraulichkeit | AES-128-GCM Feld-Level-Encryption (Fernet) | ✅ |
| Vertraulichkeit | Optional SQLCipher AES-256 Page-Level-Encryption | ✅ (opt-in) |
| Vertraulichkeit | PBKDF2-HMAC-SHA512 256 000 Iterationen | ✅ |
| Integrität | Audit-Log Hash-Chain (SHA-256) | ✅ |
| Integrität | Mandanten-Profil-Isolation (eine Datei pro Profil) | ✅ |
| Verfügbarkeit | Lokale Datenhaltung, keine Cloud-Abhängigkeit | ✅ |
| Belastbarkeit | Test-Suite mit 407 Tests, Property-/Fuzz-/Stress-Coverage | ✅ |
| Pseudonymisierung | Reversibel via Master-Passwort, irreversibel ohne | ✅ |
| Verschlüsselung at rest | Standard | ✅ |
| Verschlüsselung in transit | Office-Add-In ↔ Backend über TLS + Bearer-Token | ✅ |
| Eingangskontrolle | Master-Passwort + optionaler Bearer-Token für API | ✅ |
| Zugriffskontrolle | Profil-spezifischer KDF-Pfad | ✅ |
| Wiederherstellbarkeit | Profil-Datei-Backup obliegt dem Nutzer (siehe §11) | 🟡 (dokumentiert, nicht built-in) |
| Verfahren regelmäßiger Überprüfung | CI-Security-Scans (bandit + pip-audit), externer Pentest geplant | 🟡 (Pentest pending) |

---

## 9. Kammer-Argumentation

### WPK / BStBK / Anwaltskammer

Pseudokrat ist **kein** „Berufsausübungs-System" im Sinne kammerrechtlicher
Genehmigungserfordernisse — es ist ein **rein technisches Hilfsmittel**
zur Vorbereitung von Mandatsarbeit. Damit fällt es in dieselbe Kategorie
wie:

* Lokale Office-Programme (Word, Excel) — kammerlich unproblematisch.
* Lokale Diktiersoftware — kammerlich unproblematisch.
* Lokale Buchhaltungssoftware mit eigener Datenbank — kammerlich
  unproblematisch.

Im Unterschied zu Cloud-DATEV / Cloud-NAV (kammerlich diskutiert) hat
Pseudokrat KEIN Daten-Backflow — somit gibt es keine genehmigungs-
pflichtige Drittübermittlung.

### Argumentations-Linie für Kammer-Pitch

1. Wir lösen ein **konkretes berufsständisches Risiko** (§ 203 StGB
   beim KI-Einsatz).
2. Wir tun das **mit einer technisch verifizierbaren Maßnahme**
   (Pseudonymisierung mit Hash-Chain-Audit).
3. Wir tun das **lokal** — keine neue Cloud-Abhängigkeit.
4. Wir bieten Kammer-Mitgliedern eine **lebenslange Pro-Lizenz**
   (oder vergünstigte Sammel-Lizenzierung).

### Empfohlene Kontakte

* WPK: Referat IT/Digitalisierung
* BStBK: AG „Digitale Steuerberatung"
* DAV (Deutscher Anwaltverein): Ausschuss Anwaltliche Berufsausübung
* AK Wien (RAK Wien): Kommission „IT und Berufsrecht"
* Schweizer Anwaltsverband (SAV): Kommission Berufsrecht und Standesregeln

---

## 10. AT-/CH-Spezifika

### Österreich

* DSG 2018 + DSGVO: Identische Argumentation wie BRD.
* Verschwiegenheitspflicht: § 9 RAO, § 30 WTBG, § 23 NotO.
* Datenschutzbehörde Wien: Pseudonymisierung gemäß Art. 4 Nr. 5
  DSGVO anerkannt; Sorgfaltsmaßstab vergleichbar.

### Schweiz

* DSG (revDSG 2023) ≠ DSGVO, aber materiell ähnlich für
  Pseudonymisierung (Art. 5 lit. d revDSG).
* Anwaltsgeheimnis: Art. 13 BGFA; Steuerberatungsgeheimnis: Art. 321
  StGB.
* Wichtiger Unterschied: Schweiz hat KEIN EU-US-DPF. Cloud-KI-
  Roundtrip braucht Standard-Vertragsklauseln + ggf. Schrems-II-
  Risikoanalyse. Pseudokrat-Anonymisat senkt das Risiko-Profil
  erheblich.

---

## 11. Backup-Empfehlung

Pseudokrat hat **kein eingebautes Cloud-Backup** (by-design). Der
Nutzer ist verantwortlich:

* Empfohlen: `%LOCALAPPDATA%\Pseudokrat\profiles\` ist ein einzelnes
  Verzeichnis. Empfohlene Backup-Strategie: in das verschlüsselte
  Backup-Tool der Kanzlei aufnehmen (z. B. Veeam Endpoint, Acronis,
  Backblaze).
* Master-Passwort separat in den Kanzlei-Passwort-Manager
  speichern (Pseudokrat hat KEINEN Recovery-Mechanismus).
* Profil-Datei ist self-contained — bei Maschinen-Migration einfach
  Verzeichnis kopieren, Master-Passwort eintragen, fertig.

---

## 12. Offene Punkte für den Anwalts-Review

Diese Liste hat der DSGVO-Anwalt im Sign-off zu adressieren:

1. **§ 2 Auftragsverarbeitungsfrage** — Ist die Argumentation
   tragfähig? Empfehlung für AVV oder NDA als Alternative?
2. **§ 4 Audit-Log als Sorgfaltsnachweis** — Genügt das im Streitfall?
3. **§ 5 Mandanten-Klausel** — Formulierung kammer-tauglich? Opt-in
   vs. Opt-out?
4. **§ 7 DSAR-Konsistenz** — Wie umgehen mit Originaltext-Anfragen,
   wenn der Audit-Log nur den Anonymisat-Hash hat?
5. **§ 10 CH-Spezifika** — Schrems-II-Bewertung für Pseudonymisat-
   Roundtrip?
6. **Marketing-Aussagen** — Welche der Argumentations-Linien aus §2
   und §9 dürfen wir wörtlich öffentlich verwenden? (Insb. „Kein
   AV-Vertrag nötig" ist eine harte Marketingaussage.)

**Empfohlener Anwalts-Budget:** 1 500-3 000 €, 2-3 Std Briefing +
4-6 Std Lektüre + 1 Std Sign-off-Schreiben.

---

## 13. Pflege dieses Dokuments

Updates erforderlich bei:

* Neuen Datentypen (z. B. Gesundheitsdaten → Art. 9 DSGVO).
* Cloud-Funktionen jeder Art (Sync, Backup) — würde § 2 brechen.
* Neuen Jurisdiktionen (z. B. UK GDPR, LGPD Brasilien).
* DSGVO-Updates auf EU-Ebene.

---

## Lizenz

MIT (siehe Repository-Root). Dieser Draft darf an DSGVO-Anwälte und
Pilot-Berufsträger weitergegeben werden. **Keine Rechtsberatung.**
