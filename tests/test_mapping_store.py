"""Tests für den verschlüsselten Mapping-Store."""

from __future__ import annotations

from pathlib import Path

import pytest

from pseudokrat.store.mapping_store import MappingStore
from pseudokrat.store.secure_db import InvalidPasswordError


def test_create_and_lookup(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        m1 = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert m1.placeholder == "<COMPANY_001>"
        m2 = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert m2.placeholder == "<COMPANY_001>"
        assert m2.use_count == 2


def test_different_categories_get_different_sequences(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        a = store.get_or_create("Hofer", "PERSON")
        b = store.get_or_create("Müller", "PERSON")
        c = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert a.placeholder == "<PERSON_001>"
        assert b.placeholder == "<PERSON_002>"
        assert c.placeholder == "<COMPANY_001>"


def test_fuzzy_merge_unifies_spellings(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        a = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        b = store.get_or_create("Hofer-Bau GmbH", "COMPANY")
        c = store.get_or_create("hofer bau gmbh", "COMPANY")
        assert a.placeholder == b.placeholder == c.placeholder == "<COMPANY_001>"


def test_different_legal_forms_stay_separate(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        a = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        b = store.get_or_create("Hofer Bau GmbH & Co. KG", "COMPANY")
        assert a.placeholder != b.placeholder


def test_persistence_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        store.get_or_create("Hofer Bau GmbH", "COMPANY")

    with MappingStore(db, password="pw") as store2:
        m = store2.get_or_create("Hofer Bau GmbH", "COMPANY")
        assert m.placeholder == "<COMPANY_001>"
        assert m.use_count == 2


def test_wrong_password_raises(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="right"):
        pass
    with pytest.raises(InvalidPasswordError):
        MappingStore(db, password="wrong")


def test_find_by_placeholder(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        m = store.get_or_create("Hofer Bau GmbH", "COMPANY")
        recovered = store.find_by_placeholder(m.placeholder)
        assert recovered is not None
        assert recovered.original_text == "Hofer Bau GmbH"


def test_find_by_placeholder_missing(tmp_path: Path) -> None:
    db = tmp_path / "p.sqlite"
    with MappingStore(db, password="pw") as store:
        assert store.find_by_placeholder("<UNKNOWN_999>") is None
