"""Erzeugt die DACH-Eval-Fixtures unter ``tests/eval/fixtures/``.

Wird einmal pro Iteration manuell ausgeführt — die Output-Dateien sind
committet. Re-Run produziert byteidentische Output bei gleichem Seed.

Aufruf::

    python -m tests.eval.generate_fixtures

Erweiterung: pro Fixture-Domäne (Lohnkonto, Saldenliste, Rechnung,
Arztbrief, Versicherung) eine eigene ``build_*``-Funktion. Diese
Datei bleibt der einzige Wahrheitsort für das Fixture-Set.
"""

from __future__ import annotations

import random
from pathlib import Path

from tests.eval.fixture_builder import FixtureBuilder
from tests.eval.synth import (
    generate_at_iban,
    generate_at_svnr,
    generate_at_uid,
    generate_ch_ahv,
    generate_ch_iban,
    generate_de_iban,
    generate_de_steuer_id,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def build_lohnkonto_at(rng: random.Random) -> None:
    b = FixtureBuilder()
    dn_name = "Anna Beispielsohn"
    dn_address = "Mariahilfer Straße 88, 1070 Wien"
    employer = "Mustermann Bau GmbH"
    employer_address = "Industriestraße 12, 4020 Linz"
    employer_uid = generate_at_uid(rng)
    dn_svnr = generate_at_svnr(rng)
    salary_iban = generate_at_iban(rng)
    employer_iban = generate_at_iban(rng)
    birth_date = "15.03.1985"
    contact_email = "lohnverrechnung@mustermann-bau-at.example"
    contact_phone = "+43 732 12 34 56"

    b.add_slot("dn_name1", dn_name, "PERSON")
    b.add_slot("dn_name2", dn_name, "PERSON")  # zweites Vorkommen
    b.add_slot("dn_addr", dn_address, "ADDRESS")
    b.add_slot("emp_name", employer, "COMPANY")
    b.add_slot("emp_addr", employer_address, "ADDRESS")
    b.add_slot("emp_uid", employer_uid, "UID")
    b.add_slot("svnr", dn_svnr, "SVNR")
    b.add_slot("salary_iban", salary_iban, "IBAN")
    b.add_slot("emp_iban", employer_iban, "IBAN")
    b.add_slot("birth", birth_date, "DATE")
    b.add_slot("email", contact_email, "EMAIL")
    b.add_slot("phone", contact_phone, "PHONE")

    template = (
        "LOHNKONTO 2026\n"
        "============================================\n"
        "\n"
        "Dienstgeber:           {emp_name}\n"
        "                       {emp_addr}\n"
        "UID-Nr.:               {emp_uid}\n"
        "Kontakt:               {email} / {phone}\n"
        "\n"
        "Dienstnehmer/in:       {dn_name1}\n"
        "Geburtsdatum:          {birth}\n"
        "SV-Nummer:             {svnr}\n"
        "Wohnadresse:           {dn_addr}\n"
        "\n"
        "Gehaltszahlung an:     {salary_iban}\n"
        "DG-Verrechnungskonto:  {emp_iban}\n"
        "\n"
        "Anmerkungen zu {dn_name2}:\n"
        "  - Eintrittsdatum 01.06.2024\n"
        "  - Gehaltsstufe IV\n"
        "  - Pendlerpauschale Wien-Linz aktiv\n"
        "\n"
        "Erstellt am 31.01.2026 von der Lohnverrechnung.\n"
    )

    out = _FIXTURES_DIR / "lohnkonto_at"
    b.write_fixture(
        directory=out,
        template=template,
        description=(
            "Österreichisches Lohnkonto, 1 Dienstnehmer, alle DACH-PII-"
            "Kategorien außer ORG (Firma deckt CompanyLegalForm ab)."
        ),
        seed=101,
    )


def build_lohnkonto_de(rng: random.Random) -> None:
    b = FixtureBuilder()
    dn_name = "Friedrich Beispiel"
    dn_address = "Königsallee 47, 40212 Düsseldorf"
    employer = "Rheinmetall Mustermann AG"
    employer_address = "Werftstraße 22, 40549 Düsseldorf"
    steuer_id = generate_de_steuer_id(rng)
    iban = generate_de_iban(rng)
    bic = "DEUTDEDDXXX"
    birth_date = "07.11.1978"
    email = "lohn@rheinmetall-mustermann-de.example"

    b.add_slot("dn_name1", dn_name, "PERSON")
    b.add_slot("dn_name2", dn_name, "PERSON")
    b.add_slot("dn_addr", dn_address, "ADDRESS")
    b.add_slot("emp_name", employer, "COMPANY")
    b.add_slot("emp_addr", employer_address, "ADDRESS")
    b.add_slot("steuer_id", steuer_id, "TAX_ID")
    b.add_slot("iban", iban, "IBAN")
    b.add_slot("bic", bic, "BIC")
    b.add_slot("birth", birth_date, "DATE")
    b.add_slot("email", email, "EMAIL")

    template = (
        "LOHNABRECHNUNG Januar 2026\n"
        "============================================\n"
        "\n"
        "Arbeitgeber:           {emp_name}\n"
        "                       {emp_addr}\n"
        "Kontakt Lohn:          {email}\n"
        "\n"
        "Arbeitnehmer:          {dn_name1}\n"
        "Anschrift:             {dn_addr}\n"
        "Geburtsdatum:          {birth}\n"
        "Steuer-ID:             {steuer_id}\n"
        "\n"
        "Auszahlung an:         IBAN {iban} (BIC {bic})\n"
        "\n"
        "Bemerkung: {dn_name2} ist seit 2018 in der Lohngruppe E12.\n"
    )

    out = _FIXTURES_DIR / "lohnkonto_de"
    b.write_fixture(
        directory=out,
        template=template,
        description="Deutsche Lohnabrechnung mit Steuer-ID und DE-IBAN.",
        seed=202,
    )


def build_versicherung_ch(rng: random.Random) -> None:
    b = FixtureBuilder()
    name = "Markus Beispielmann"
    address = "Bahnhofstrasse 14, 8001 Zürich"
    ahv = generate_ch_ahv(rng)
    iban = generate_ch_iban(rng)
    email = "kunde@beispielversicherung-ch.example"
    birth = "22.08.1972"

    b.add_slot("name1", name, "PERSON")
    b.add_slot("name2", name, "PERSON")
    b.add_slot("addr", address, "ADDRESS")
    b.add_slot("ahv", ahv, "AHV")
    b.add_slot("iban", iban, "IBAN")
    b.add_slot("email", email, "EMAIL")
    b.add_slot("birth", birth, "DATE")

    template = (
        "Krankenkassen-Vertragsantrag\n"
        "=============================\n"
        "\n"
        "Antragsteller:        {name1}\n"
        "Adresse:              {addr}\n"
        "Geburtsdatum:         {birth}\n"
        "AHV-Nummer:           {ahv}\n"
        "Prämien-Belastung:    {iban}\n"
        "Kontakt:              {email}\n"
        "\n"
        "{name2} bestätigt mit seiner Unterschrift die Richtigkeit.\n"
    )
    out = _FIXTURES_DIR / "versicherung_ch"
    b.write_fixture(
        directory=out,
        template=template,
        description="Schweizer Krankenkassen-Antrag mit AHV und CH-IBAN.",
        seed=303,
    )


def build_false_positive_traps(rng: random.Random) -> None:
    """Texte, die Recognizer KEINE PII-Spans erzeugen sollten.

    Erwartete Spans: leer. Trifft der Detector hier ein false-positive,
    fließt das direkt in die FP-Rate ein.
    """
    del rng  # nicht benötigt — kein Synth-Wert in diesem Fixture
    b = FixtureBuilder()
    template = (
        "Wir haben heute beim Hofer-Markt Wien eingekauft. Die Müller-Schiene\n"
        "an der Kasse 3 war defekt. Bauer-Land-Speck war aus.\n"
        "\n"
        "ATU ohne Ziffern, GmbH ohne Firmennamen davor.\n"
        "Eine IBAN-Anleitung ohne konkrete IBAN.\n"
        "DE12 ist keine Steuer-ID.\n"
        "\n"
        "Ein Test mit Goethestraße 5 (ohne PLZ und Ort) sollte nicht als\n"
        "vollständige Adresse durchgehen.\n"
    )
    out = _FIXTURES_DIR / "false_positive_traps"
    b.write_fixture(
        directory=out,
        template=template,
        description=(
            "Sätze mit Quasi-PII (Markennamen mit Bindestrich, halbe Adressen, "
            "PII-Wörter ohne Werte) — Recognizer dürfen hier nichts taggen."
        ),
        seed=None,
    )


def main() -> None:
    _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260527)
    build_lohnkonto_at(rng)
    build_lohnkonto_de(rng)
    build_versicherung_ch(rng)
    build_false_positive_traps(rng)
    print(f"Fixtures geschrieben unter {_FIXTURES_DIR}")


if __name__ == "__main__":
    main()
