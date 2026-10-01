# Abnahmematrix für den vollständigen Arbeitsablauf

Stand: 1. Oktober 2026. Ziel bleibt die produktive Verarbeitung der tatsächlichen
Excel-Arbeitsmappen in die tatsächliche Word-Vorlage. Die vorhandenen Tests sind
keine Ersatzdefinition dieses Ziels. Originale und lokale Abnahmebelege bleiben
auf dem Spark.

| Anforderung | Vorhandene Evidenz | Noch erforderlicher Abschlussnachweis |
| --- | --- | --- |
| Identitäten pseudonymisieren und exakt zurückwandeln | Projektablauf und Regressionstests; synthetische Mappe mit 100 Blättern und 46.080 Identitätszellen geprüft | Lokaler Vergleich repräsentativer Originale, inklusive Kennungstypen und fachlicher Beziehungen; Wiederherstellung mit gesichertem Schlüssel |
| Rechenwerte unverändert lassen | Synthetischer Vergleich von Werten, Typen und Formeln; separate Kennungsbehandlung | Lokale Prüfung von identifizierenden Zahlen gegenüber Rechenwerten; Zahlenkombinationen bleiben möglicherweise wiedererkennbar |
| Excel- und Word-Metadaten berücksichtigen | Bereinigung von Dokumenteigenschaften, Excel-Autorenkennungen und unbenutztem Textspeicher; unbekannte Funktionen blockieren | Tatsächliche Dateien einschließlich versteckter Blätter, Bilder, Beziehungen und Zusatzteile lokal untersuchen; blockierte Funktionen nicht still entfernen |
| Formeln zuverlässig auswerten | Explizite Windows-Excel- und Linux-Calc-Adapter; native Tests; Quelldateien bleiben unverändert | Ergebnisse der benötigten Formeln auf der Spark-Installation gegen unabhängig festgelegte Sollwerte prüfen; Engine-Unterschiede klären |
| Word-Tabellen und Kennzahlen befüllen | Generator mit geprüfter Zuordnung, dynamischen Zeilen und Quellennachweisen | Vollständige echte Quellen-Ziel-Zuordnung samt Einheiten, Zeiträumen, Filtern, Rundung und Änderungsfällen lokal abnehmen |
| Automatisch formulierte Texte | Deterministische, bedingte Textregeln implementiert und getestet | Freie lokale Modelltexte sind noch nicht integriert; tatsächliche API und fachliche Prüfregeln fehlen. Textregeln ersetzen nicht jede gewünschte freie Formulierung |
| Bericht mit mehr als 60 Seiten | Nativer synthetischer 65-Seiten-Durchlauf inklusive PDF und Seitenfeldern bestanden, auch aus installiertem Wheel | Echte Vorlage vollständig rendern und visuell prüfen: Schriften, Tabellenumbrüche, Bilder, Kopf-/Fußzeilen, benötigte Verzeichnisse und weitere Office-Funktionen |
| Keine Originale an zentrale KI | Lokaler Ablauf und Baumeister-Übergabe dokumentiert; kein zentraler Modellaufruf im Berichtspfad | Netzwerkgrenzen, Backups, Zugriffsrechte, Modellbetrieb und Diagnosewege auf der tatsächlichen Maschine prüfen |
| Installation auf dem Spark | Linux-x86_64-Paketinstallation und synthetischer Selbsttest unter WSL bestanden | Installation mit passenden Abhängigkeiten und Selbsttest auf dem tatsächlichen Spark; WSL ist kein Architektur- oder Betriebsnachweis dafür |
| Bedienbarer produktiver Ablauf | CLI für Bestandsaufnahme, Bericht, Vorschau und Selbsttest vorhanden; keine Ausgabeüberschreibung | Ablauf mit dem Anwender und realen Dateien prüfen, einschließlich Fehlerbehandlung, notwendigen manuellen Schritten und Wiederanlauf |
| Mindestens 95 Prozent automatische Erledigung | Messregeln in LOKALE-ABNAHME.md festgelegt | Vorab festgelegte repräsentative Fallmenge vollständig auswerten; blockierte Fälle und Inhaltskorrekturen mitzählen; Prüfzeit separat erfassen |
| Produktionsfreigabe | Synthetische Prüfungen und CI-Evidenz in PRODUKTIONSSTATUS.md | Alle benötigten Funktionen implementiert, tatsächliche Umgebung und Dateien abgenommen, offene fachliche oder Datenschutzfehler behoben |

## Nächste lokale Rückmeldung

Zunächst den synthetischen Selbsttest aus [Spark-Betrieb](SPARK-BETRIEB.md)
ausführen. Sein Ergebnis prüft die Installation, nicht die echten Dateien.
Für die Modellanbindung werden Dienst/Protokoll und lokale API-Adresse benötigt;
Modellnamen allein bestimmen keine aufrufbare Schnittstelle. Zugangsschlüssel
bleiben lokal.

Die echte Bestandsaufnahme und Zuordnung dürfen anschließend ausschließlich
vor Ort geprüft werden. Benötigte, noch blockierte Dokumentfunktionen anhand
unabhängiger künstlicher Beispiele nachstellen. Keine Originalinventare,
Fehlerauszüge, Mappings oder Berichtsteile an die zentrale KI weitergeben.

Eine hundertprozentige Anonymitätsgarantie bei reversiblen Zuordnungen und
unveränderten Merkmalskombinationen ist kein erfüllbares Freigabekriterium.
Die Architektur hält deshalb Originaldaten und echte Ergebnisse lokal; auch
deren Betriebsumgebung braucht einen überprüften Schutz.
