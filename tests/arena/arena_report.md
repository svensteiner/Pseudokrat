# Pseudokrat — Anonymisierungs-Nachweis (Testarena)

**Ergebnis (realistischer Korpus):** BESTANDEN — 0 Lecks

- Lauf-Zeitpunkt: 2026-06-25 07:36 UTC
- Seed (reproduzierbar): `0`
- Geprüfte Dokumente: **1500**
- Geprüfte Geheimnisse (PII-Werte): **9668**
- Durchgerutschte Geheimnisse (Lecks): **0**
- Leck-Quote: **0.0000%**
- Roundtrip-Fehler (Rückübersetzung): **0**
- Python: 3.12.8 · Windows

## Nach Härtegrad (Formatierungs-Modus)

| Modus | Geheimnisse | Lecks |
|---|---:|---:|
| clean | 2436 | 0 |
| labelbreak | 2399 | 0 |
| spacing | 2436 | 0 |
| table | 2397 | 0 |

## Nach PII-Kategorie

| Kategorie | Geheimnisse | Lecks |
|---|---:|---:|
| ADDRESS | 1500 | 0 |
| AHV | 166 | 0 |
| BIC | 500 | 0 |
| BIRTHDATE | 750 | 0 |
| COMPANY | 1000 | 0 |
| EMAIL | 1000 | 0 |
| IBAN | 1250 | 0 |
| PERSON | 2250 | 0 |
| PHONE | 500 | 0 |
| STEUER_ID | 83 | 0 |
| SVNR | 334 | 0 |
| UID | 252 | 0 |
| UST_ID | 83 | 0 |

## Interpretation

Über alle Vorlagen, Formatierungs-Modi und Länder (AT/DE/CH) hinweg ist kein einziger der eingebauten PII-Werte im anonymisierten Text verblieben — auch nicht über Zeilenumbrüche oder ungewöhnliche Abstände zerrissen. Jede Rückübersetzung hat das Original exakt wiederhergestellt.

## Reflow-Stress (separat, nicht im Pass/Fail-Tor)

Extremfall: numerische Werte (z. B. IBAN) mitten im Wert durch einen Zeilenumbruch zerrissen. Bewusst hart; zeigt die Robustheit gegen ungünstige Umbrüche.

- Dokumente: 300 · Geheimnisse: 1935
- Lecks im Reflow-Stress: **182**

---
_PII-Werte sind synthetisch (erfunden), durchlaufen aber die echten Prüfziffer-Verfahren. Geprüft wird die Text-Pipeline; Datei-Formate (PDF/DOCX/XLSX) nutzen dieselbe Engine (siehe `tests/test_formats_*`)._