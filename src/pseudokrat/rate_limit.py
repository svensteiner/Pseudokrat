"""Thread-safer Token-Bucket-Rate-Limiter für den lokalen HTTP-Server.

Schließt F-001 aus dem Self-Audit (siehe SELF_AUDIT.md / D-038). Der lokale
Server bindet zwar auf Loopback, kann aber unter Multi-User-OS oder bei
lokalem RCE-Vektor weiterhin durch Brute-Force-Anfragen erschöpft werden.
Ein einfacher Token-Bucket pro ``ServerState`` setzt eine harte Obergrenze
auf Anfragen-pro-Sekunde und erlaubt kurze Bursts.

Die Implementierung ist absichtlich dependency-frei — keine ``slowapi``,
keine ``redis``-Backends. Pseudokrat ist lokal, der Limiter darf simpel
sein.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock

#: Default-Werte: 60 Tokens Bucket-Kapazität, 1 Token/Sekunde Refill.
#: Im Steady-State => 60 Requests/Minute. Burst von 60 Requests möglich,
#: was für einen Excel-Add-in-Workflow (Spalte-für-Spalte) ausreicht.
DEFAULT_BURST = 60
DEFAULT_REFILL_PER_SEC = 1.0


@dataclass
class RateLimitDecision:
    """Resultat eines Bucket-Versuchs."""

    allowed: bool
    retry_after_seconds: float


class TokenBucket:
    """Thread-safer Token-Bucket.

    Bucket fasst ``capacity`` Tokens, refilled mit ``refill_per_sec``
    Tokens pro Sekunde bis maximal ``capacity``. Jeder Request konsumiert
    einen Token. Wenn der Bucket leer ist, wird die Anfrage abgelehnt
    und ``retry_after_seconds`` enthält die Zeit bis zum nächsten Token.
    """

    def __init__(
        self,
        capacity: int = DEFAULT_BURST,
        refill_per_sec: float = DEFAULT_REFILL_PER_SEC,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity muss > 0 sein")
        if refill_per_sec <= 0:
            raise ValueError("refill_per_sec muss > 0 sein")
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()
        self._lock = Lock()

    def try_consume(self, n: float = 1.0) -> RateLimitDecision:
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last)
            self._last = now
            self._tokens = min(
                float(self.capacity), self._tokens + elapsed * self.refill_per_sec
            )
            if self._tokens >= n:
                self._tokens -= n
                return RateLimitDecision(allowed=True, retry_after_seconds=0.0)
            needed = n - self._tokens
            retry = needed / self.refill_per_sec
            return RateLimitDecision(allowed=False, retry_after_seconds=retry)

    @property
    def tokens(self) -> float:
        """Aktueller Bucket-Füllstand inkl. ausstehendem Refill."""
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last)
            self._last = now
            self._tokens = min(
                float(self.capacity), self._tokens + elapsed * self.refill_per_sec
            )
            return self._tokens


def bucket_from_env(
    *,
    burst_env: str = "PSEUDOKRAT_SERVER_RATE_BURST",
    rps_env: str = "PSEUDOKRAT_SERVER_RATE_RPS",
    default_burst: int = DEFAULT_BURST,
    default_rps: float = DEFAULT_REFILL_PER_SEC,
    clock: Callable[[], float] = time.monotonic,
) -> TokenBucket:
    """Baut einen Token-Bucket aus Env-Vars mit safe Defaults."""
    burst = _int_env(burst_env, default_burst)
    rps = _float_env(rps_env, default_rps)
    return TokenBucket(capacity=burst, refill_per_sec=rps, clock=clock)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


__all__ = (
    "DEFAULT_BURST",
    "DEFAULT_REFILL_PER_SEC",
    "RateLimitDecision",
    "TokenBucket",
    "bucket_from_env",
)
