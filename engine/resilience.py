"""Resilience primitives for ArcaneaClaw — retry, circuit breaker, rate limiter.

Every external call in the fleet should go through these wrappers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger("arcanea-claw.resilience")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
):
    """Decorator for retrying sync functions with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            delay = base_delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_attempts, exc,
                        )
                        raise
                    logger.warning(
                        "%s attempt %d/%d failed: %s — retrying in %.1fs",
                        func.__name__, attempt, max_attempts, exc, delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exc  # type: ignore[misc]

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject calls fast
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker for external service calls.

    Usage:
        cb = CircuitBreaker(name="gemini", failure_threshold=3, reset_timeout=60)
        if cb.can_execute():
            try:
                result = call_gemini(...)
                cb.record_success()
            except Exception as e:
                cb.record_failure()
                raise
    """

    name: str
    failure_threshold: int = 5
    reset_timeout: float = 60.0  # seconds before trying again
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _success_count: int = field(default=0, init=False)

    def can_execute(self) -> bool:
        """Check if a call should be attempted."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.reset_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit %s: OPEN → HALF_OPEN (testing recovery)", self.name)
                return True
            return False

        # HALF_OPEN: allow one test call
        return True

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit %s: HALF_OPEN → CLOSED (recovered)", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("Circuit %s: HALF_OPEN → OPEN (still failing)", self.name)
        elif self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit %s: CLOSED → OPEN (%d failures in a row)",
                self.name, self._failure_count,
            )

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "state": self._state.value,
            "failures": self._failure_count,
            "successes": self._success_count,
        }


# ---------------------------------------------------------------------------
# Rate Limiter (token bucket)
# ---------------------------------------------------------------------------

@dataclass
class RateLimiter:
    """Token bucket rate limiter for API calls.

    Usage:
        limiter = RateLimiter(name="gemini", rate=10, per=60)  # 10 calls per 60s
        limiter.wait()  # blocks until a token is available
        call_gemini(...)
    """

    name: str
    rate: int           # tokens per window
    per: float = 60.0   # window in seconds
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self._tokens = float(self.rate)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill_amount = elapsed * (self.rate / self.per)
        self._tokens = min(float(self.rate), self._tokens + refill_amount)
        self._last_refill = now

    def acquire(self) -> bool:
        """Try to acquire a token. Returns True if granted, False if rate limited."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    def wait(self, timeout: float = 30.0) -> bool:
        """Block until a token is available or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.acquire():
                return True
            time.sleep(0.1)
        logger.warning("Rate limiter %s: timed out after %.1fs", self.name, timeout)
        return False

    @property
    def stats(self) -> dict[str, Any]:
        self._refill()
        return {
            "name": self.name,
            "tokens_remaining": round(self._tokens, 1),
            "rate": f"{self.rate}/{self.per}s",
        }


# ---------------------------------------------------------------------------
# Global registry — shared across all skills
# ---------------------------------------------------------------------------

_circuits: dict[str, CircuitBreaker] = {}
_limiters: dict[str, RateLimiter] = {}


def get_circuit(name: str, **kwargs: Any) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _circuits:
        _circuits[name] = CircuitBreaker(name=name, **kwargs)
    return _circuits[name]


def get_limiter(name: str, **kwargs: Any) -> RateLimiter:
    """Get or create a named rate limiter."""
    if name not in _limiters:
        _limiters[name] = RateLimiter(name=name, **kwargs)
    return _limiters[name]


def all_circuit_stats() -> list[dict]:
    return [cb.stats for cb in _circuits.values()]


def all_limiter_stats() -> list[dict]:
    return [rl.stats for rl in _limiters.values()]


# ---------------------------------------------------------------------------
# Convenience: resilient external call wrapper
# ---------------------------------------------------------------------------

def resilient_call(
    func: Callable[..., T],
    *args: Any,
    circuit_name: str = "default",
    rate_name: str | None = None,
    max_retries: int = 3,
    **kwargs: Any,
) -> T | None:
    """Execute a function with circuit breaker, rate limiter, and retry.

    Returns None if the circuit is open or all retries fail.
    """
    circuit = get_circuit(circuit_name)
    if not circuit.can_execute():
        logger.debug("Circuit %s is OPEN — skipping %s", circuit_name, func.__name__)
        return None

    if rate_name:
        limiter = get_limiter(rate_name)
        if not limiter.wait(timeout=10.0):
            logger.debug("Rate limited on %s — skipping %s", rate_name, func.__name__)
            return None

    last_exc: Exception | None = None
    delay = 1.0

    for attempt in range(1, max_retries + 1):
        try:
            result = func(*args, **kwargs)
            circuit.record_success()
            return result
        except Exception as exc:
            last_exc = exc
            circuit.record_failure()
            if attempt < max_retries:
                logger.warning(
                    "%s attempt %d/%d: %s — retry in %.1fs",
                    func.__name__, attempt, max_retries, exc, delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 30.0)

                if not circuit.can_execute():
                    logger.warning("Circuit %s opened during retries — aborting", circuit_name)
                    return None

    logger.error("%s failed after %d attempts: %s", func.__name__, max_retries, last_exc)
    return None
