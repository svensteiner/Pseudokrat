"""PII-Recognizer für DACH-spezifische Entitäten."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pseudokrat.recognizers.address import AddressRecognizer
from pseudokrat.recognizers.at_konto_blz import AustrianKontoBlzRecognizer
from pseudokrat.recognizers.at_register import AustrianRegisterRecognizer
from pseudokrat.recognizers.at_steuernummer import AustrianSteuernummerRecognizer
from pseudokrat.recognizers.at_svnr import AustrianSVNRRecognizer
from pseudokrat.recognizers.at_uid import AustrianUIDRecognizer
from pseudokrat.recognizers.base import Recognizer, Span
from pseudokrat.recognizers.bic import BICRecognizer
from pseudokrat.recognizers.birthdate import BirthDateRecognizer
from pseudokrat.recognizers.ch_ahv import SwissAHVRecognizer
from pseudokrat.recognizers.company import CompanyLegalFormRecognizer
from pseudokrat.recognizers.creditcard import CreditCardRecognizer
from pseudokrat.recognizers.de_steuer_id import GermanSteuerIdRecognizer
from pseudokrat.recognizers.de_ust_id import GermanUStIdNrRecognizer
from pseudokrat.recognizers.email import EmailRecognizer
from pseudokrat.recognizers.escaped_placeholder import EscapedPlaceholderRecognizer
from pseudokrat.recognizers.firmenbuch import FirmenbuchRecognizer
from pseudokrat.recognizers.iban import IBANDachRecognizer
from pseudokrat.recognizers.mandanten_nr import MandantenNummerRecognizer
from pseudokrat.recognizers.person import PersonRecognizer
from pseudokrat.recognizers.person_name import GazetteerNameRecognizer
from pseudokrat.recognizers.phone import PhoneRecognizer
from pseudokrat.recognizers.secret import SecretRecognizer
from pseudokrat.recognizers.url import UrlRecognizer

if TYPE_CHECKING:  # pragma: no cover
    from pseudokrat.store.mapping_store import MappingStore


def default_recognizers() -> list[Recognizer]:
    """Standard-Bundle aller eingebauten Recognizer (ohne MandantenNummer)."""
    return [
        EscapedPlaceholderRecognizer(),
        IBANDachRecognizer(),
        BICRecognizer(),
        AustrianUIDRecognizer(),
        AustrianSVNRRecognizer(),
        AustrianSteuernummerRecognizer(),
        FirmenbuchRecognizer(),
        AustrianRegisterRecognizer(),
        AustrianKontoBlzRecognizer(),
        GermanSteuerIdRecognizer(),
        GermanUStIdNrRecognizer(),
        SwissAHVRecognizer(),
        CreditCardRecognizer(),
        EmailRecognizer(),
        PhoneRecognizer(),
        UrlRecognizer(),
        SecretRecognizer(),
        CompanyLegalFormRecognizer(),
        BirthDateRecognizer(),
        PersonRecognizer(),
        GazetteerNameRecognizer(),
        AddressRecognizer(),
    ]


class InvalidMandantenPatternError(ValueError):
    """Ein konfigurierter Mandanten-Nr-Regex ist nicht kompilierbar."""


def compile_mandanten_pattern(pattern: str) -> re.Pattern[str]:
    """Kompiliere ein per-Profil-Mandanten-Pattern. Eigene Exception für CLI-Mapping."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise InvalidMandantenPatternError(
            f"Mandanten-Pattern ist kein gültiger Regex: {exc}"
        ) from exc


def recognizers_for_store(store: MappingStore) -> list[Recognizer]:
    """Standard-Bundle plus profilspezifischer Mandanten-Nr-Recognizer.

    Wenn das Profil in ``profile_metadata`` einen Eintrag unter
    :data:`pseudokrat.store.profile.MANDANTEN_PATTERN_METADATA_KEY` hat, wird
    ein :class:`MandantenNummerRecognizer` mit diesem Pattern angehängt.
    """
    from pseudokrat.store.profile import MANDANTEN_PATTERN_METADATA_KEY

    bundle = default_recognizers()
    pattern = store.get_metadata(MANDANTEN_PATTERN_METADATA_KEY)
    if pattern:
        bundle.append(MandantenNummerRecognizer(compile_mandanten_pattern(pattern)))
    return bundle


__all__ = [
    "InvalidMandantenPatternError",
    "Recognizer",
    "Span",
    "AddressRecognizer",
    "AustrianSVNRRecognizer",
    "AustrianUIDRecognizer",
    "BICRecognizer",
    "BirthDateRecognizer",
    "CompanyLegalFormRecognizer",
    "EmailRecognizer",
    "EscapedPlaceholderRecognizer",
    "GermanSteuerIdRecognizer",
    "GermanUStIdNrRecognizer",
    "IBANDachRecognizer",
    "MandantenNummerRecognizer",
    "PersonRecognizer",
    "PhoneRecognizer",
    "SecretRecognizer",
    "SwissAHVRecognizer",
    "UrlRecognizer",
    "compile_mandanten_pattern",
    "default_recognizers",
    "recognizers_for_store",
]
