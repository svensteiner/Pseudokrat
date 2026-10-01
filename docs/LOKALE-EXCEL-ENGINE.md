# Lokale Neuberechnung mit Microsoft Excel

Der optionale Python-Baustein `pseudokrat.native_excel.recalculate(Path(...))`
berechnet eine geprüfte XLSX-Arbeitskopie mit installiertem Microsoft Excel
unter Windows neu. Er gibt Formelwerte, Engine-Version und Eingabe-SHA-256
zurück. Diese Ergebnisse sind vertraulich und bleiben lokal.

Die Originaldatei wird nicht in Excel geöffnet oder verändert. Der bestehende
Berichtsgenerator verwendet diesen Baustein **noch nicht** und blockiert weiterhin
Formelquellen. Ein zurückgegebenes Ergebnis ist keine Produktionsfreigabe.

Vor Excel werden die strengen OOXML-Grenzen und alle zugelassenen Formelcontainer
geprüft, einschließlich bedingter Formatierungen und Datenvalidierung. Externe
Verknüpfungen, Makros und nicht unterstützte Bestandteile werden abgewiesen.
Iterative Berechnungen und „Genauigkeit wie angezeigt“ sind nicht unterstützt.
Verborgene Blätter werden ausschließlich in der verworfenen Arbeitskopie sichtbar
gemacht, damit Zirkelbezüge geprüft werden können.

Die neue Excel-Instanz erhält vor dem Öffnen deaktivierte Makros, Ereignisse
und Linkaktualisierung. Ein Windows-Job beendet die zugeordnete Instanz beim
Ende des Workers, auch bei dessen Timeout. Bereits vorhandene Excel-Prozesse
werden nicht übernommen. Das ist keine Netzwerksperre: Office selbst muss in
der Betriebsumgebung separat gegen unerwünschten Netzwerkverkehr isoliert werden.

Live-Tests ausschließlich mit synthetischen Dateien:

```powershell
$env:PSEUDOKRAT_TEST_EXCEL='1'
.venv\Scripts\pytest.exe tests/test_native_excel.py -q
```

Ohne diese Freigabe überspringen die Tests den tatsächlichen Excel-Start.
Die Engine arbeitet mit Excels Zahlenpräzision; eine fachliche Prüfung der
Rundung und Eingabegenauigkeit bleibt notwendig. Der Baustein ist noch nicht
für die automatische Berichtsfreigabe zugelassen. Insbesondere fehlen dafür
Integration, Lastabnahme und Prüfung mit repräsentativen Originalen.
Eine verfügbare Windows-Engine beweist keine Verfügbarkeit auf dem Spark.

Leere Formelergebnisse werden derzeit als fehlende Pflichtwerte abgewiesen,
auch wenn eine Formel absichtlich einen Leerstring erzeugt. Die Live-Abnahme
unter Excel 16.0 umfasst Summe, negative Rundung, Text, versteckte Blätter,
Fehlerzellen sowie direkte und indirekte Zirkelbezüge. Zusammen mit den
Mapping-, Tabellen- und Berichtstests bestanden am 01.10.2026 34 Tests.
Dies deckt weder sämtliche Excel-Funktionen noch sämtliche Zirkelvarianten ab.

Ein zusätzlicher Live-Test erzwingt einen Timeout, nachdem die eigene
Excel-Instanz die Arbeitskopie geöffnet hat. Er prüft, dass die konkrete
Prozess-ID verschwunden ist, das temporäre Arbeitsverzeichnis entfernt wurde
und die Originalbytes unverändert bleiben. Der Test verwendet ausschließlich
einen instrumentierten Test-Worker; im ausgelieferten Worker gibt es keinen
Schlaf- oder Debug-Schalter. Das Verhalten bei einem Hänger während der
COM-Aktivierung vor der Job-Zuordnung ist damit noch nicht abgenommen.

Die Eingabe wird begrenzt eingelesen; Parser, Arbeitskopie und Ergebnis-Hash
beziehen sich auf denselben Byte-Snapshot. Ändert sich die Originaldatei während
des Laufs, wird das Ergebnis verworfen. Fehlende, strukturierte, leere oder
nicht endliche Formelwerte werden ebenfalls abgewiesen.
