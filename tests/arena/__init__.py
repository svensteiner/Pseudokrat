"""Pseudokrat Testarena — adversariale Zero-Leak-Prüfung.

Die Arena ist **kein** Eval auf gelabelten Beispielen (das macht
``tests/eval/``), sondern ein gegnerischer Belastungstest:

1. Erzeuge hunderte/tausende realistische DACH-Dokumente, jedes aus
   **bekannten** PII-Geheimnissen zusammengebaut (Ground Truth).
2. Schicke jedes Dokument durch die **echte** Anonymizer-Pipeline.
3. Leck-Tor: Kein Geheimnis darf im Output überleben — wörtlich oder
   normalisiert (z. B. über Zeilenumbruch zerrissen).
4. Roundtrip: De-Anonymisierung stellt das Original exakt wieder her.
5. Nachweis-Report (JSON + Markdown).

Der Härtegrad entscheidet, wie fies die Dokumente formatiert sind
(``clean``/``spacing``/``table``/``labelbreak``).
"""
