"""Eval-Harness — strukturierte DACH-Fixtures + Scoring fuer das Production-Ready-Gate.

Pakage-Layout:

* ``fixtures/`` — Klartext, JSON Ground-Truth, generierte Binaer-Dateien.
* ``synth.py``  — Generatoren fuer gueltige IBANs/SVNR/Steuer-IDs/UIDs
                  (mit korrekten Pruefziffern), damit Fixtures nicht
                  am Recognizer-Mod-Check scheitern.
* ``scoring.py``— Span-Level Precision/Recall/F1.
"""
