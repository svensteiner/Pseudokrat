"""Tests für die Fuzzy-Match-Logik."""

from __future__ import annotations

import pytest

from pseudokrat.fuzzy import (
    core_company_name,
    extract_legal_form,
    is_fuzzy_merge_category,
    normalize,
    should_merge,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hofer Bau GmbH", "hofer bau gmbh"),
        ("Hofer-Bau GmbH", "hofer bau gmbh"),
        ("hofer  bau   GmbH", "hofer bau gmbh"),
        ("Café Mozart", "cafe mozart"),
        ("Müller & Söhne KG", "mueller & soehne kg"),
        ("Straßenwacht", "strassenwacht"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_extract_legal_form_finds_gmbh() -> None:
    assert extract_legal_form("hofer bau gmbh") == "gmbh"


def test_extract_legal_form_finds_compound() -> None:
    assert extract_legal_form("acme gmbh & co. kg") == "gmbh & co. kg"


def test_extract_legal_form_none() -> None:
    assert extract_legal_form("acme corporation worldwide") is None


def test_core_company_name() -> None:
    assert core_company_name("hofer bau gmbh") == "hofer bau"


def test_should_merge_exact_match() -> None:
    assert should_merge("hofer bau gmbh", "hofer bau gmbh", "COMPANY")


def test_should_merge_close_levenshtein() -> None:
    # Tippfehler-Toleranz
    assert should_merge("hofer bau gmbh", "hoferbau gmbh", "COMPANY")


def test_should_merge_rejects_different_legal_forms() -> None:
    """Hofer Bau GmbH und Hofer Bau GmbH & Co. KG dürfen nicht gemerged werden."""
    assert not should_merge(
        "hofer bau gmbh",
        "hofer bau gmbh & co. kg",
        "COMPANY",
    )


def test_should_merge_rejects_too_distant_names() -> None:
    assert not should_merge("hofer bau gmbh", "schmidt steuer gmbh", "COMPANY")


# --- D-048: PERSON/ADDRESS dürfen NICHT fuzzy-mergen ---


@pytest.mark.parametrize("category", ["PERSON", "ADDRESS", "DATE", "IBAN", "UID"])
def test_non_company_categories_are_not_fuzzy(category: str) -> None:
    assert not is_fuzzy_merge_category(category)


@pytest.mark.parametrize("category", ["COMPANY", "ORG"])
def test_company_categories_are_fuzzy(category: str) -> None:
    assert is_fuzzy_merge_category(category)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("maier", "mayer"),  # Levenshtein 1 — verschiedene Personen
        ("meier", "meyer"),
        ("mueller", "mahler"),
    ],
)
def test_similar_persons_do_not_merge(a: str, b: str) -> None:
    """Maier ≠ Mayer: ähnliche, aber verschiedene Nachnamen bleiben getrennt."""
    assert not should_merge(a, b, "PERSON")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("hauptstrasse 12", "hauptstrasse 13"),  # verschiedene Hausnummern
        ("hauptstrasse 12", "hauptgasse 12"),
    ],
)
def test_similar_addresses_do_not_merge(a: str, b: str) -> None:
    assert not should_merge(a, b, "ADDRESS")


def test_same_person_exact_normalized_still_merges() -> None:
    """Echte Schreibvarianten DERSELBEN Person mergen weiterhin via Exact-Pfad.

    normalize() faltet Umlaut/Groß-Klein/Whitespace — der Vergleich läuft
    hier bereits auf der normalisierten Form, also greift der Exact-Match.
    """
    assert normalize("Müller") == normalize("müller") == normalize("MÜLLER")
    norm = normalize("Müller")
    assert should_merge(norm, norm, "PERSON")


def test_same_address_exact_normalized_still_merges() -> None:
    assert normalize("Hauptstraße 12") == normalize("hauptstrasse  12")
    norm = normalize("Hauptstraße 12")
    assert should_merge(norm, norm, "ADDRESS")
