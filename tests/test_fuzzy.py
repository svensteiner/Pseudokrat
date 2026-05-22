"""Tests für die Fuzzy-Match-Logik."""

from __future__ import annotations

import pytest

from pseudokrat.fuzzy import (
    core_company_name,
    extract_legal_form,
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
