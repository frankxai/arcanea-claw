"""Tests for engine.resilience — CircuitBreaker, RateLimiter, retry decorator."""

from __future__ import annotations

import time
from unittest.mock import patch, MagicMock

import pytest

from engine.resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    retry,
    resilient_call,
    get_circuit,
    get_limiter,
    _circuits,
    _limiters,
)


# ── CircuitBreaker ──────────────────────────────────────────────────────────


class TestCircuitBreaker:
    """State-machine tests for CircuitBreaker."""

    def test_starts_closed(self):
        cb = CircuitBreaker(name="test")
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_after_reaching_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_open_rejects_calls(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_open_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.1)
        cb.record_failure()
        assert cb.state == "open"

        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == "half_open"

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        cb.can_execute()  # triggers HALF_OPEN
        assert cb.state == "half_open"

        cb.record_success()
        assert cb.state == "closed"
        assert cb._failure_count == 0

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, reset_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        cb.can_execute()  # triggers HALF_OPEN

        cb.record_failure()
        assert cb.state == "open"

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb._success_count == 1

    def test_stats_property(self):
        cb = CircuitBreaker(name="demo")
        cb.record_success()
        stats = cb.stats
        assert stats["name"] == "demo"
        assert stats["state"] == "closed"
        assert stats["successes"] == 1
        assert stats["failures"] == 0

    def test_full_lifecycle_closed_open_half_closed(self):
        """Complete lifecycle: closed -> open -> half_open -> closed."""
        cb = CircuitBreaker(name="lifecycle", failure_threshold=2, reset_timeout=0.05)

        # Phase 1: closed
        assert cb.state == "closed"

        # Phase 2: fail until open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"

        # Phase 3: wait for half_open
        time.sleep(0.06)
        assert cb.can_execute() is True
        assert cb.state == "half_open"

        # Phase 4: succeed to close
        cb.record_success()
        assert cb.state == "closed"


# ── RateLimiter ─────────────────────────────────────────────────────────────


class TestRateLimiter:
    """Token-bucket rate limiter tests."""

    def test_acquire_succeeds_when_tokens_available(self):
        rl = RateLimiter(name="test", rate=5, per=1.0)
        assert rl.acquire() is True

    def test_acquire_depletes_tokens(self):
        rl = RateLimiter(name="test", rate=2, per=60.0)
        assert rl.acquire() is True
        assert rl.acquire() is True
        assert rl.acquire() is False

    def test_tokens_refill_over_time(self):
        rl = RateLimiter(name="test", rate=10, per=1.0)
        # Drain all tokens
        for _ in range(10):
            rl.acquire()
        assert rl.acquire() is False

        # Wait for partial refill
        time.sleep(0.15)
        assert rl.acquire() is True

    def test_tokens_never_exceed_rate(self):
        rl = RateLimiter(name="test", rate=3, per=1.0)
        time.sleep(0.2)  # Let some "extra" time pass
        rl._refill()
        assert rl._tokens <= 3.0

    def test_wait_returns_true_when_token_available(self):
        rl = RateLimiter(name="test", rate=5, per=1.0)
        assert rl.wait(timeout=0.5) is True

    def test_wait_times_out_when_no_tokens(self):
        rl = RateLimiter(name="test", rate=1, per=60.0)
        rl.acquire()  # drain
        assert rl.wait(timeout=0.2) is False

    def test_stats_property(self):
        rl = RateLimiter(name="demo", rate=10, per=60.0)
        stats = rl.stats
        assert stats["name"] == "demo"
        assert stats["rate"] == "10/60.0s"
        assert stats["tokens_remaining"] <= 10.0


# ── retry decorator ─────────────────────────────────────────────────────────


class TestRetryDecorator:
    """Tests for the @retry decorator."""

    def test_succeeds_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def always_ok():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert always_ok() == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def fail_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        assert fail_then_ok() == "ok"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        @retry(max_attempts=2, base_delay=0.01)
        def always_fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            always_fail()

    def test_only_retries_specified_exceptions(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, retryable_exceptions=(ValueError,))
        def wrong_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            wrong_error()
        assert call_count == 1  # no retries for TypeError

    def test_exponential_backoff_delays(self):
        """Verify that delay doubles between attempts (within tolerance)."""
        timestamps = []

        @retry(max_attempts=3, base_delay=0.05, backoff_factor=2.0, max_delay=10.0)
        def track_time():
            timestamps.append(time.monotonic())
            if len(timestamps) < 3:
                raise ValueError("retry me")
            return "done"

        track_time()
        assert len(timestamps) == 3

        # First gap should be ~0.05s, second ~0.10s
        gap1 = timestamps[1] - timestamps[0]
        gap2 = timestamps[2] - timestamps[1]
        assert gap1 >= 0.04  # base_delay with tolerance
        assert gap2 >= 0.08  # doubled delay with tolerance


# ── resilient_call ──────────────────────────────────────────────────────────


class TestResilientCall:
    """Tests for the convenience resilient_call wrapper."""

    def setup_method(self):
        """Clear global registries between tests."""
        _circuits.clear()
        _limiters.clear()

    def test_successful_call(self):
        result = resilient_call(lambda: 42, circuit_name="test_ok", max_retries=1)
        assert result == 42

    def test_returns_none_when_circuit_open(self):
        cb = get_circuit("test_open", failure_threshold=1)
        cb.record_failure()
        assert cb.state == "open"

        result = resilient_call(lambda: 42, circuit_name="test_open")
        assert result is None

    def test_retries_then_fails(self):
        call_count = 0

        def bad():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with patch("engine.resilience.time.sleep"):
            result = resilient_call(bad, circuit_name="test_retry_fail", max_retries=3)

        assert result is None
        assert call_count == 3

    def test_with_rate_limiter(self):
        rl = get_limiter("test_rl", rate=100, per=1.0)
        result = resilient_call(
            lambda: "ok",
            circuit_name="test_rl_circuit",
            rate_name="test_rl",
        )
        assert result == "ok"


# ── Global registry ─────────────────────────────────────────────────────────


class TestGlobalRegistry:

    def setup_method(self):
        _circuits.clear()
        _limiters.clear()

    def test_get_circuit_creates_once(self):
        cb1 = get_circuit("alpha", failure_threshold=5)
        cb2 = get_circuit("alpha")
        assert cb1 is cb2

    def test_get_limiter_creates_once(self):
        rl1 = get_limiter("beta", rate=10, per=60)
        rl2 = get_limiter("beta")
        assert rl1 is rl2
