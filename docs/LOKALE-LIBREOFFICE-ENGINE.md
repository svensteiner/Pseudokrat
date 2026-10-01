# Experimenteller Linux-Adapter für LibreOffice Calc

`pseudokrat.native_libreoffice.recalculate(Path(...))` berechnet eine geprüfte
XLSX-Arbeitskopie unter Linux neu. Der Berichtsgenerator verwendet ihn ausdrücklich
mit `--recalculate-libreoffice` (Python: `recalculate_libreoffice=True`).
Dies bedeutet keine Produktionsfreigabe.

Voraussetzungen im getesteten Ubuntu-System: `/usr/bin/python3` mit
`python3-uno` und `/usr/bin/libreoffice` mit Calc. Getestete Engine:
LibreOffice 24.2.7.2 unter Ubuntu/WSL auf x86-64. Dies ist kein Nachweis für
die tatsächliche Spark-Hardware oder deren CPU-Architektur.

Beispiel im installierten Linux-Projekt:

```bash
python -m pseudokrat.local_report --excel daten.xlsx --template vorlage.docx --mapping mapping.json --output neuer-bericht --recalculate-libreoffice
```

Die Optionen `--recalculate-excel` und `--recalculate-libreoffice` schließen
sich gegenseitig aus. Bei Fehlern erfolgt weder ein Wechsel zur anderen Engine
noch eine Übernahme alter Formel-Caches. Ohne Engine-Auswahl bleiben
Formelquellen gesperrt. Engine, Version, Eingabehash und verwendete Formeln
werden bei den betreffenden Feldern im vertraulichen Berichtsnachweis erfasst.

Die Originaldatei wird begrenzt eingelesen und gehasht. Die identischen Bytes
durchlaufen die gemeinsame OOXML- und Formelprüfung. Erst die daraus neu
geschriebene Arbeitskopie wird geöffnet, mit einem privaten Profil, deaktivierten
Makros und Linkaktualisierungen. Eine lokale UNO-Pipe dient zur Steuerung; es
wird kein Netzwerk-Listener geöffnet. Der Prozess selbst benötigt dennoch eine
separate Netzwerkisolation in der Betriebsumgebung.

Der Worker ruft `calculateAll()` auf und liest alle Formelzellen aus. Fehler in
einer beliebigen Formel blockieren das gesamte Ergebnis. Engine-Version und
Originalhash werden mit den Ergebnissen zurückgegeben. Originale werden nicht
überschrieben. Eine neue Prozessgruppe enthält Worker und Office-Prozess;
Timeout und regulärer Abschluss bereinigen ausschließlich diese Gruppe.

## Typprüfung und derzeitige Einschränkungen

LibreOffice stellt boolesche Formelergebnisse bei einem überschriebenen
Zahlenformat über UNO als normale Zahlen dar. Deshalb wird jede Formel nur
in der Arbeitskopie mit einer `ISLOGICAL`-Prüfung umgeben. Ein logischer Wert
erzeugt damit einen Fehler und blockiert die Ausgabe. Gewöhnliche Zahlen- und
Textergebnisse behalten ihren Wert. LibreOffice 24.2 behandelt auch `--TRUE()`
bei dieser Prüfung noch als logisch; solche impliziten Typumwandlungen werden
derzeit blockiert und benötigen weitere Kompatibilitätsarbeit.

Die Prüfung wertet den Ausdruck zweimal aus. Daher sind volatile Funktionen
`RAND`, `RANDBETWEEN`, `RANDARRAY`, `NOW`, `TODAY`, `CELL` und `INFO` aktuell
gesperrt. Boolesche Quellzellen sind ebenfalls gesperrt, bis deren Importtyp
zuverlässig unterstützt wird. Formelinspektion wie `FORMULATEXT` ist durch die
gemeinsame Funktionsliste nicht zugelassen und darf nicht ohne Prüfung der
internen Formeländerung ergänzt werden. Iterative Berechnung, reduzierte
Genauigkeit und weitere unbekannte Office-Funktionen bleiben blockiert.

Der zusätzliche Formelaufwand kann große Dateien verlangsamen. Lasttests,
vollständige Excel/Calc-Kompatibilitätsprüfung und reale Spark-Abnahme fehlen.
Ein kompletter Absturz des steuernden Betriebssystems ist nicht durch den
Timeout-Test abgedeckt. Die Dateien im temporären Profil sind vertraulich.

## Live-Abnahme mit synthetischen Dateien

```bash
PSEUDOKRAT_TEST_LIBREOFFICE=1 python -m pytest tests/test_native_libreoffice.py -q
```

Ohne ausdrückliche Aktivierung oder außerhalb von Linux werden die Tests
übersprungen. Geprüft werden frische XLSX-Ergebnisse, Rundung, Text,
versteckte Blätter, unveränderte Originalbytes, Fehler- und Boolfälle sowie
Timeout nach dem Öffnen. Der Timeout-Test prüft, dass keine eigene Instanz
weiterläuft und die Arbeitskopie entfernt wurde.

API-Grundlagen: [Neuberechnung](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1sheet_1_1XCalculatable.html),
[Ladeoptionen](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1document_1_1MediaDescriptor.html),
[Formelergebnistypen](https://api.libreoffice.org/docs/idl/ref/namespacecom_1_1sun_1_1star_1_1sheet_1_1FormulaResult.html).
