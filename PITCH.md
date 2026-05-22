# Pseudokrat — Warum es das trotzdem braucht

**Einseiter, Mai 2026**

---

## Das vermeintliche Argument dagegen

„OpenAI lässt mich Training auf meinen Daten abschalten — und jetzt bringen sie sogar
einen eigenen Anonymisierer raus. Wozu noch ein lokales Tool?"

Klingt plausibel. Stimmt nicht.

---

## Warum „Training-Opt-Out" nicht reicht

Training-Opt-Out heißt: *Deine Daten landen nicht im nächsten GPT.*
Es heißt **nicht**:

- Deine Daten verlassen Österreich nicht. Sie gehen nach Texas, Virginia, Iowa.
- Deine Daten werden nicht gespeichert. OpenAI hält Logs **bis zu 30 Tage** für
  „Abuse Monitoring" — Anthropic ähnlich. Bei US-Subpoena (CLOUD Act) trotzdem
  herausgabepflichtig, egal was der Vertrag sagt.
- Deine Daten sind sicher vor Insidern. Sind sie nie, in keinem Cloud-Dienst.
- Die DSGVO ist erfüllt. Ist sie nicht. Schrems II + DPF-Wackler heißt: jeder
  US-Transfer von personenbezogenen Daten ist auditierbar problematisch.

Für **Berufsträger mit Verschwiegenheitspflicht** ist „Opt-out vom Training" kein
Argument. Die Pflicht lautet:

> Daten dürfen den Geheimnisträger nicht in identifizierbarer Form verlassen.

§ 91 WTBG (Steuerberater AT), § 9 RAO (Anwälte AT), § 54 ÄrzteG, § 203 StGB DE.
**Verstoß = strafbar.** Nicht „Bußgeld nach DSGVO". Strafbar.

---

## OpenAI bringt selbst einen Verschlüssler — bestätigt nur das Problem

Dass OpenAI im April 2026 den **„Private Mode"-Filter** angekündigt hat, ist die
beste Marketing-Kampagne, die wir uns wünschen konnten. Sie sagen damit öffentlich:

> *„Ja, ihr habt recht — wir sollten die PII nicht sehen."*

Aber: **Der OpenAI-Filter läuft in der OpenAI-Cloud.** Das heißt, dein Text geht
trotzdem zu OpenAI, wird dort entschlüsselt (für den Filter), maskiert, weitergegeben
ans Modell, und am Ende rückübersetzt. **Zwei Sekunden lang lag der Klartext auf
einem fremden Server.** Das reicht für jeden Berufshaftpflichtversicherer, um den
Versicherungsschutz im Schadenfall zu kürzen.

Pseudokrat läuft **lokal**. Der Klartext verlässt deine Maschine nie. Das ist nicht
„auch eine Variante" — das ist der einzige Modus, der die Verschwiegenheitspflicht
juristisch sauber erfüllt.

---

## Wo OpenAIs Filter konkret zu wenig anonymisiert

Wir haben den OpenAI-Privacy-Filter und Microsoft Presidio out-of-the-box gegen
typische DACH-Mandantenkorrespondenz getestet. Was sie **nicht erkennen**:

| Was wir fanden | OpenAI / Presidio | Pseudokrat |
|---|---|---|
| Österreichische UID „ATU12345675" | ❌ ignoriert | ✅ erkannt, Prüfziffer validiert |
| AT-Sozialversicherungsnummer (10-stellig) | ❌ als Telefonnummer fehlklassifiziert | ✅ mod-11-Prüfziffer |
| Schweizer AHV-Nummer „756.xxxx.xxxx.xx" | ❌ ignoriert | ✅ EAN-13-Prüfung |
| Deutsche Steuer-Identifikationsnummer (§ 139b AO) | ⚠️ inkonsistent | ✅ ISO 7064 Mod 11,10 |
| „Hofer Bau GmbH & Co. KG" | ⚠️ teilweise als Organisation | ✅ vollständig, Rechtsform-bewusst |
| „Hofer-Bau GmbH" und „Hofer Bau GmbH" als **dieselbe** Firma | ❌ zwei Platzhalter | ✅ Fuzzy-Merge |
| Mandantennummer „M-2024-0815" | ❌ ignoriert | ✅ konfigurierbar pro Kanzlei |
| Konsistente Pseudonymisierung über mehrere Sessions | ❌ nicht persistent | ✅ verschlüsselter Mapping-Store pro Mandat |
| Reversibilität (KI-Antwort zurückübersetzen) | ❌ nicht möglich | ✅ Hotkey, einklick-deanonymisierung |
| Audit-Log für Berufshaftpflicht | ❌ nicht vorhanden | ✅ Hash-verkettet, exportierbar |

Das ist kein Polishing-Problem. Das sind **strukturelle Lücken**, die ein generisches
Tool ohne DACH-Spezialwissen nicht schließen kann.

---

## Speziell für Österreich

Österreich ist kein „kleines Deutschland". Die UID startet mit ATU, nicht DE. Die
Sozialversicherungsnummer hat 10 Stellen, nicht 11. Die Rechtsformen kennen
e.U. (eingetragener Unternehmer) und OG (offene Gesellschaft), die Deutschland nicht
hat. Die Berufsrechte sind anders strukturiert — die WPK-Berichtspflicht im
Schadenfall greift früher als bei der deutschen WPK.

Das wichtigste: **Die WKÖ-Kammern und die Berufshaftpflichtversicherer** sind die
Gatekeeper. Ein lokaler Anbieter mit AT-Sitz und AT-spezifischer Compliance hat hier
einen Heimspielvorteil, den OpenAI strukturell nie haben wird.

---

## Was Pseudokrat ist (in einem Satz)

> Pseudokrat ist die Schaltzentrale zwischen Berufsträger und Cloud-KI:
> Es entfernt vor dem Versand jede identifizierbare Information, hält das Mapping
> verschlüsselt lokal, und übersetzt die KI-Antwort wieder zurück — alles unter
> Berufshaftpflicht-tauglicher Audit-Dokumentation.

---

## Markt-Differenzierer in Stichworten

1. **Lokal-only**, kein Phone-Home, keine Telemetry.
2. **DACH-Recognizer** mit Prüfziffer-Validierung — der einzige Anbieter, der das
   tut.
3. **Reversible Pseudonymisierung** mit verschlüsseltem Mapping-Store pro
   Mandant. CamoText kann das nicht. OpenAI kann das nicht. Niemand kann das.
4. **Hash-verketteter Audit-Log** für Berufshaftpflichtversicherer und
   Kammeraudits.
5. **KI-agnostisch** — Pseudokrat funktioniert mit ChatGPT, Claude, Gemini, Le Chat,
   Mistral und jeder weiteren Cloud-KI gleichermaßen. Kein Vendor-Lock-in.
6. **Offen für Kanzleien**: Mandantennummern, interne Aktenzeichen, eigene
   PII-Patterns konfigurierbar pro Profil.

---

## Warum jetzt

Drei Trends, alle drei rückenwindig:

- **Berufshaftpflichtversicherer** beginnen 2026, KI-Nutzung explizit auszuschließen
  oder mit Compliance-Nachweis zu verknüpfen. Pseudokrat liefert genau diesen
  Nachweis.
- **Die WTBG-Novelle 2026** schärft die Verschwiegenheitspflicht in Hinblick auf
  digitale Hilfsmittel. Kanzleien suchen ein Tool, das man der Kammer zeigen kann.
- **OpenAIs eigener Filter ist ein Werbeplakat**: Sie sagen öffentlich, dass das
  Problem real ist. Wir lösen es richtig.

---

*Pseudokrat — damit Ihre Mandanten auch in der Cloud anonym bleiben.*
