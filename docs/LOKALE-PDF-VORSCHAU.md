# Lokale PDF-Vorschau

Der erzeugte DOCX-Bericht kann unter Linux mit LibreOffice Writer als vertrauliche
PDF-Vorschau gerendert werden. Originaldatei und gespeicherte DOCX-Feldwerte bleiben
unverändert. Die Vorschau ist keine fachliche oder visuelle Freigabe.

Voraussetzungen: installierte Pseudokrat-Abhängigkeiten, `/usr/bin/libreoffice`,
LibreOffice Writer und für `/usr/bin/python3` verfügbares `python3-uno`.

```bash
python -m pseudokrat.report_preview --input /lokal/bericht.docx --output /lokal/neue-vorschau
```

Der Ausgabeordner darf noch nicht existieren. `preview.pdf` und `preview.json`
bleiben ausschließlich lokal. Der Nachweis enthält Seitenzahl, Engine-Version,
Dateihashes und ausdrücklich `production_approved: false`, `visual_reviewed: false`
sowie `source_docx_updated: false`.

Die Verarbeitung nutzt eine geprüfte Arbeitskopie, ein separates Office-Profil,
deaktivierte Makros und Linkaktualisierung sowie eine begrenzte Laufzeit.
Nicht unterstützte Dokumentbestandteile und offene Platzhalter stoppen den Lauf.
Nach Ende oder Timeout wird die eigene Prozessgruppe beendet. Dies ersetzt keine
Netzwerkisolation des Rechners. Eingebettete Bilder bleiben vertrauliche Inhalte.

Writer aktualisiert die zugelassenen Seitenfelder in der Arbeitskopie vor dem
PDF-Export. Layout, Schriften, Tabellenumbrüche und Vollständigkeit müssen lokal
visuell geprüft werden; Microsoft Word kann anders umbrechen. Die angeforderte
Feldaktualisierung ist kein allgemeiner Nachweis korrekter Feldwerte jeder Vorlage.

Verifikation unter Ubuntu/WSL mit LibreOffice 24.2.7.2: vier Live-Tests bestanden.
Sie prüfen Berichte mit drei und 65 Seiten, absichtlich falsche gespeicherte
Seitenzahlen (beim 65-Seiten-Fall zusätzlich gesperrte Felder), unveränderte
DOCX-Quelldateien, offene Platzhalter sowie Timeout und Prozessbereinigung.
Eine Abnahme auf dem Spark mit echten Vorlagen steht weiterhin aus.

Technische Grundlagen: [Writer reformat](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1text_1_1XTextDocument.html)
und [LibreOffice PDF-Exportparameter](https://help.libreoffice.org/latest/de/text/shared/guide/pdf_params.html).
