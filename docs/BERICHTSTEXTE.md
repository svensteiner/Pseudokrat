# Automatische Berichtstexte aus geprüften Fakten

Zuordnungsversion 3 ergänzt fachlich geprüfte Textbausteine und Zahlenbedingungen.
Es gibt keinen Modellaufruf und keine Ausführung von Python, Jinja oder anderem
Code aus der Zuordnung. Der gesamte Ablauf bleibt lokal. Die zentrale KI kann
Textregeln anhand synthetischer Beispiele entwickeln; der Nutzer prüft deren
fachliche Bedeutung lokal vor dem Setzen von `reviewed: true`.

Die Word-Vorlage enthält zum Beispiel `{{ assessment }}`. Eine vollständige
Zuordnung für eine Kennzahl lautet:

```json
{
  "version": 3,
  "reviewed": true,
  "template_sha256": "LOKALEN_HASH_DER_WORD_VORLAGE_EINTRAGEN",
  "headers": {"Daten": {"B1": "Saldo EUR"}},
  "fields": {
    "amount": {"sheet": "Daten", "range": "B2", "operation": "cell", "format": "decimal", "decimals": 2}
  },
  "narratives": {
    "assessment": {
      "cases": [
        {"field": "amount", "op": "gt", "value": "0", "template": "Der Saldo ist positiv und beträgt {{ amount }} EUR."},
        {"field": "amount", "op": "lt", "value": "0", "template": "Der Saldo ist negativ und beträgt {{ amount }} EUR."}
      ],
      "otherwise": "Der Saldo ist ausgeglichen und beträgt {{ amount }} EUR."
    }
  }
}
```

Aufruf wie beim [Berichtsgenerator](LOKALER-BERICHTSGENERATOR.md). Formelquellen
benötigen weiterhin die ausdrücklich aktivierte lokale Neuberechnung.

Alternativ besteht eine Regel nur aus `{"template": "Der Saldo beträgt {{ amount }} EUR."}`.
Bei Version 3 kann zusätzlich die `tables`-Zuordnung aus Version 2 verwendet werden.
Textregeln referenzieren skalare `fields`, keine dynamischen Tabellenzeilen oder
andere Textregeln. Benötigte Summen müssen explizit als Feld zugeordnet werden.

## Entscheidungsregeln

- Operatoren: `eq`, `ne`, `lt`, `le`, `gt`, `ge`.
- Schwellenwerte sind Dezimalzeichenketten mit Punkt, beispielsweise `"0.05"`.
- Verglichen wird der ungerundete `exact_value` der Kennzahl. Die Ausgabe benutzt
  das konfigurierte Anzeigeformat. Ein kleiner positiver Betrag kann daher als
  `0,00` erscheinen; Schwellen und Rundung müssen fachlich zueinander passen.
- Genau eine passende Bedingung wählt deren Text. Bei keiner passenden Bedingung
  gilt `otherwise`. Mehrere passende Bedingungen stoppen den Lauf.
- Alle Zweige werden auf Referenzen und Syntax geprüft, auch nicht ausgewählte.
- Jede Textregel muss mindestens ein Quellenfeld verwenden, im Text oder in einer
  Bedingung. Fehlende oder ungeeignete Werte führen zum Abbruch.
- Grenzen: 200 Textregeln, 30 Bedingungen je Regel, 20.000 Zeichen je Textvorlage
  und 100.000 Zeichen je ausgefülltem Text. Texte werden in vorhandene Word-
  Absätze eingesetzt; mehrteilige Abschnitts-Layouts sind damit nicht abgedeckt.

## Nachweis und Grenzen

`nachweis.json` enthält unter `narratives` den ausgegebenen Text, den gewählten
Zweig, den Textbaustein, alle geprüften Bedingungen und die verwendeten Feldnamen.
Die vollständigen Quellenfakten bleiben unter `facts` erhalten. Ein Feld muss
im Word-Dokument oder als Eingabe einer Textregel verwendet werden. Jede
definierte Textregel muss im Word-Dokument vorkommen.

Der Generator prüft Zahlen und Regelmechanik, nicht die Wahrheit beliebiger
Behauptungen in einem Textbaustein. Ursachen, Bewertungen, Einheiten und Aussagen
müssen fachlich geprüft werden. Freie lokale KI-Formulierungen samt semantischer
Prüfung sind noch nicht implementiert. Ausgaben bleiben vertrauliche Entwürfe
mit `production_approved: false` bis zur lokalen fachlichen und visuellen Abnahme.
