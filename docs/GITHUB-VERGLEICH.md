# Vergleich verwandter Projekte

Recherche: 30. September 2026. Dies ist ein Architekturvergleich, kein
vollständiges Sicherheitsaudit. Es wurde kein fremder Quellcode übernommen.

| Projekt | Lizenz laut Repository | Nutzen für Pseudokrat / Abgrenzung |
| --- | --- | --- |
| [Presidio](https://github.com/data-privacy-stack/presidio) | MIT | Erweiterbare Erkennung und Ersetzungen; Erkennung allein garantiert keine vollständige Entfernung. Interessanter optionaler Erkennungsadapter. |
| [local-llm-xlsx-anonymizer](https://github.com/PrzeMusz/local-llm-xlsx-anonymizer) | MIT | Lokale KI und manuelle Begriffsliste für Excel. Konzept übernommen: eigene KI schlägt Kandidaten vor; Pseudokrat hält die Zuordnung verschlüsselt statt als exportierbare Klartextdatei. |
| [DocGuard](https://github.com/AlexLiuTT/docguard) | MIT | Reversible Platzhalter in Office-Dateien; Referenz für Verarbeitung über XML-Textläufe hinweg. Formatversprechen müssen am eigenen Korpus geprüft werden. |
| [mask-engine](https://github.com/noirdoc-ai/mask-engine) | MIT | Deutsche Erkennung und versteckte OOXML-Kanäle. Frühes Projekt; nützlich für zusätzliche Testfälle und Detektoren. |
| [doc-sanitizer](https://github.com/cogniflow-ai/doc-sanitizer) | MIT | Lokale Maskierung/Rückwandlung und verschlüsselte Zuordnung. Architekturvergleich für lokale Datentrennung. |
| [Lethe](https://github.com/moonlight-lupin/lethe) | Apache-2.0 | Lokaler reversibler Datentresor. Dokumentierte Grenzen etwa bei Bildern in Office-Dateien müssen separat berücksichtigt werden. |
| [python-docx-template](https://github.com/elapouya/python-docx-template) | LGPL-2.1 | Kandidat für spätere Word-Berichtserzeugung aus geprüfter Vorlage; keine Anonymisierungslösung. Lizenzbedingungen vor Integration beachten. |
| [LLM Guard](https://github.com/protectai/llm-guard) | siehe Repository | Bei Recherche archiviert; deshalb keine neue Kernabhängigkeit. |

## Entscheidung

Pseudokrat verwendet seine vorhandenen Profile, Verschlüsselung und Recognizer
weiter. Der neue Office-Projektmodus ergänzt projektweite Tokens, unveränderte
numerische XML-Werte, neutrale Blattnamen, Hash-Prüfung vor Freigabe und einen
getrennten lokalen Original-Arbeitsordner. Die lokale KI-Anbindung ist optional.

Keine der verglichenen Lösungen belegt für unseren unbekannten Dokumentbestand
95 Prozent automatische Bearbeitung oder garantierte Nicht-Zuordenbarkeit bei
unveränderten Zahlen. Das muss mit lokal markierten echten Dokumenten gemessen
werden. Zusätzliche Erkennungsmodelle sind erst sinnvoll, wenn dieser Vergleich
konkrete Lücken zeigt; mehr Modelle ersetzen keine Überprüfung der Exportdatei.
