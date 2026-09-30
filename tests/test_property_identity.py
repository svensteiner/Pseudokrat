"""Apartment identifiers must disappear without changing calculation values."""

import pytest

from pseudokrat.recognizers.property_identity import PropertyIdentityRecognizer, field_kind


@pytest.mark.parametrize("text", [
    "Top 17", "Wohnung Nr. A-17", "Objekt-Nr.: 00127", "Stiege 2", "Tür 8",
    "Einheit B/12", "Musterstraße 12", "Mariahilfer Straße 17/2",
])
def test_property_identifiers_are_detected(text):
    spans = PropertyIdentityRecognizer().analyze(text)
    assert spans
    assert any(span.text == text for span in spans)


@pytest.mark.parametrize("text", ["Miete 1200,50 EUR", "Fläche 72,4 m²", "Rendite 3,5 %", "Wohnung 80 m²"])
def test_calculation_values_are_not_identifiers(text):
    assert not PropertyIdentityRecognizer().analyze(text)


@pytest.mark.parametrize("header", ["Top", "Wohnungsnummer", "Objekt-ID", "Adresse", "PLZ", "Ort", "Etage", "Mieter", "Eigentümer"])
def test_identity_fields(header):
    assert field_kind(header) == "identity"


@pytest.mark.parametrize("header", ["Wohnfläche", "Nutzfläche m²", "Nettomiete", "Miete EUR", "Baujahr"])
def test_property_fingerprints_are_flagged_but_not_changed(header):
    assert field_kind(header) == "quasi_identifier"


def test_ordinary_financial_field():
    assert field_kind("Betriebskosten") == "value"
