"""Validiert die synthetischen PII-Generatoren.

Die Eval-Fixtures sind nur aussagekräftig, wenn die generierten Werte
*formal gültig* sind — sonst würden die Recognizer (z. B. IBAN-Mod-97)
sie verwerfen und wir messen Recall am falschen Bottleneck.
"""

from __future__ import annotations

import random

from tests.eval.synth import (
    _ahv_check_digit,
    _at_uid_check_digit,
    _steuer_id_check_digit,
    _svnr_check_digit,
    generate_at_iban,
    generate_at_svnr,
    generate_at_uid,
    generate_ch_ahv,
    generate_ch_iban,
    generate_de_iban,
    generate_de_steuer_id,
    iban_mod97_ok,
    synth_entities,
)


def test_iban_generators_pass_mod97() -> None:
    rng = random.Random(0)
    for _ in range(50):
        assert iban_mod97_ok(generate_at_iban(rng))
        assert iban_mod97_ok(generate_de_iban(rng))
        assert iban_mod97_ok(generate_ch_iban(rng))


def test_iban_country_and_length_correct() -> None:
    rng = random.Random(1)
    at = generate_at_iban(rng)
    de = generate_de_iban(rng)
    ch = generate_ch_iban(rng)
    assert at.startswith("AT") and len(at) == 20
    assert de.startswith("DE") and len(de) == 22
    assert ch.startswith("CH") and len(ch) == 21


def test_svnr_has_valid_check_digit() -> None:
    rng = random.Random(2)
    for _ in range(20):
        svnr = generate_at_svnr(rng)
        assert len(svnr) == 10
        # Layout: seq(3) + check(1) + birth(6)
        seq = svnr[:3]
        check = int(svnr[3])
        birth = svnr[4:]
        assert _svnr_check_digit(seq + birth) == check
        assert check < 10  # 10 ist kein erlaubter SVNR-Prüfwert


def test_at_uid_check_digit_correct() -> None:
    rng = random.Random(3)
    for _ in range(20):
        uid = generate_at_uid(rng)
        assert uid.startswith("ATU")
        assert len(uid) == 11
        digits = uid[3:]
        assert _at_uid_check_digit(digits[:7]) == int(digits[7])


def test_de_steuer_id_check_digit_correct() -> None:
    rng = random.Random(4)
    for _ in range(20):
        tid = generate_de_steuer_id(rng)
        assert len(tid) == 11
        assert tid[0] != "0"  # erste Stelle darf nicht 0 sein
        assert _steuer_id_check_digit(tid[:10]) == int(tid[10])


def test_ch_ahv_check_digit_correct() -> None:
    rng = random.Random(5)
    for _ in range(20):
        ahv = generate_ch_ahv(rng)
        # Format: "756.XXXX.XXXX.XXY" mit Y = Prüfziffer
        bare = ahv.replace(".", "")
        assert bare.startswith("756")
        assert len(bare) == 13
        assert _ahv_check_digit(bare[:12]) == int(bare[12])


def test_synth_entities_reproducible_across_runs() -> None:
    """Selber Seed → identisches Set. Eval-Fixtures müssen reproduzierbar sein."""
    a = list(synth_entities(seed=42))
    b = list(synth_entities(seed=42))
    assert a == b


def test_synth_entities_different_seeds_yield_different_sets() -> None:
    a = list(synth_entities(seed=1))
    b = list(synth_entities(seed=2))
    assert a != b


# --- Cross-Validation: Synth-Werte werden von echten Recognizern akzeptiert -


def test_synth_uid_accepted_by_recognizer() -> None:
    from pseudokrat.recognizers.at_uid import is_valid_at_uid

    rng = random.Random(6)
    for _ in range(20):
        uid = generate_at_uid(rng)
        assert is_valid_at_uid(uid), f"Recognizer lehnt UID ab: {uid}"


def test_synth_steuer_id_accepted_by_recognizer() -> None:
    from pseudokrat.recognizers.de_steuer_id import is_valid_de_steuer_id

    rng = random.Random(7)
    for _ in range(20):
        tid = generate_de_steuer_id(rng)
        assert is_valid_de_steuer_id(tid), f"Recognizer lehnt Steuer-ID ab: {tid}"


def test_synth_iban_accepted_by_recognizer() -> None:
    from pseudokrat.recognizers.iban import is_valid_iban

    rng = random.Random(8)
    for _ in range(20):
        for iban in (generate_at_iban(rng), generate_de_iban(rng), generate_ch_iban(rng)):
            assert is_valid_iban(iban), f"Recognizer lehnt IBAN ab: {iban}"


def test_synth_svnr_accepted_by_recognizer() -> None:
    from pseudokrat.recognizers.at_svnr import is_valid_at_svnr

    rng = random.Random(9)
    for _ in range(20):
        svnr = generate_at_svnr(rng)
        assert is_valid_at_svnr(svnr), f"Recognizer lehnt SVNR ab: {svnr}"


def test_synth_ahv_accepted_by_recognizer() -> None:
    from pseudokrat.recognizers.ch_ahv import is_valid_ch_ahv

    rng = random.Random(10)
    for _ in range(20):
        ahv = generate_ch_ahv(rng)
        assert is_valid_ch_ahv(ahv), f"Recognizer lehnt AHV ab: {ahv}"
