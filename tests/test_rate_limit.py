"""Unit-Tests für ``pseudokrat.rate_limit``."""

from __future__ import annotations

import pytest

from pseudokrat.rate_limit import (
    DEFAULT_BURST,
    DEFAULT_REFILL_PER_SEC,
    TokenBucket,
    bucket_from_env,
)


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_bucket_rejects_invalid_construction() -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=0)
    with pytest.raises(ValueError):
        TokenBucket(capacity=5, refill_per_sec=0)


def test_bucket_starts_full_and_drains() -> None:
    clock = _FakeClock()
    bucket = TokenBucket(capacity=3, refill_per_sec=1.0, clock=clock)
    assert bucket.try_consume().allowed is True
    assert bucket.try_consume().allowed is True
    assert bucket.try_consume().allowed is True
    decision = bucket.try_consume()
    assert decision.allowed is False
    # Mit 1 token/s und null Tokens dauert es ~1 s bis wieder einer da ist.
    assert decision.retry_after_seconds == pytest.approx(1.0, abs=0.001)


def test_bucket_refills_over_time() -> None:
    clock = _FakeClock()
    bucket = TokenBucket(capacity=2, refill_per_sec=1.0, clock=clock)
    bucket.try_consume()
    bucket.try_consume()
    assert bucket.try_consume().allowed is False
    clock.advance(2.0)
    assert bucket.try_consume().allowed is True
    assert bucket.try_consume().allowed is True


def test_bucket_caps_at_capacity_when_idle() -> None:
    clock = _FakeClock()
    bucket = TokenBucket(capacity=5, refill_per_sec=2.0, clock=clock)
    bucket.try_consume()
    clock.advance(1000.0)
    # Nach langer Idle-Zeit darf der Bucket nicht über die Kapazität wachsen.
    assert bucket.tokens == pytest.approx(5.0)


def test_retry_after_proportional_to_deficit() -> None:
    clock = _FakeClock()
    bucket = TokenBucket(capacity=1, refill_per_sec=0.5, clock=clock)
    bucket.try_consume()  # leert
    decision = bucket.try_consume()
    assert decision.allowed is False
    # 0.5 token/s → 2 s pro Token.
    assert decision.retry_after_seconds == pytest.approx(2.0, abs=0.001)


def test_bucket_from_env_uses_defaults_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PSEUDOKRAT_SERVER_RATE_BURST", raising=False)
    monkeypatch.delenv("PSEUDOKRAT_SERVER_RATE_RPS", raising=False)
    bucket = bucket_from_env()
    assert bucket.capacity == DEFAULT_BURST
    assert bucket.refill_per_sec == DEFAULT_REFILL_PER_SEC


def test_bucket_from_env_applies_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSEUDOKRAT_SERVER_RATE_BURST", "10")
    monkeypatch.setenv("PSEUDOKRAT_SERVER_RATE_RPS", "5.5")
    bucket = bucket_from_env()
    assert bucket.capacity == 10
    assert bucket.refill_per_sec == pytest.approx(5.5)


def test_bucket_from_env_ignores_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PSEUDOKRAT_SERVER_RATE_BURST", "garbage")
    monkeypatch.setenv("PSEUDOKRAT_SERVER_RATE_RPS", "-3")
    bucket = bucket_from_env()
    assert bucket.capacity == DEFAULT_BURST
    assert bucket.refill_per_sec == DEFAULT_REFILL_PER_SEC
