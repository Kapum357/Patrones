"""
Circuit Breaker + Bulkhead SMS Gateway.

Architecture:
  ┌─────────────────────────────────────────────┐
  │               SMS Gateway                   │
  │                                             │
  │  send_otp_sms(phone, message)               │
  │       │                                     │
  │       ▼                                     │
  │  [Circuit Breaker: Aldeamo]                 │
  │       │ CLOSED → try Aldeamo                │
  │       │ OPEN   → skip, go to Twilio         │
  │       │                                     │
  │       ▼ (on success)                        │
  │   return result                             │
  │       │ (on failure / OPEN circuit)         │
  │       ▼                                     │
  │  [Bulkhead Semaphore: Twilio]               │
  │       │                                     │
  │       ▼                                     │
  │   try Twilio (fallback)                     │
  └─────────────────────────────────────────────┘

State is persisted to CircuitBreakerState model for the dashboard.
"""
import logging
import threading
from typing import Tuple
import requests

import pybreaker
from django.conf import settings
from django.utils import timezone

from otp.models import CircuitBreakerState, SmsProvider

logger = logging.getLogger(__name__)

# ── Bulkhead: limit concurrent calls per provider ─────────────────────────────
_aldeamo_semaphore = threading.Semaphore(5)   # max 5 concurrent Aldeamo calls
_twilio_semaphore = threading.Semaphore(10)   # max 10 concurrent Twilio calls

# ── pybreaker listeners ───────────────────────────────────────────────────────

class _DBStateListener(pybreaker.CircuitBreakerListener):
    """Persists circuit state changes to the database."""

    def __init__(self, provider: str):
        self.provider = provider

    def state_change(self, cb, old_state, new_state):
        old_name = old_state if isinstance(old_state, str) else old_state.name
        new_name = new_state if isinstance(new_state, str) else new_state.name
        logger.warning(
            f"[CircuitBreaker] {self.provider}: {old_name} → {new_name}"
        )
        try:
            state_str = new_name.upper().replace("-", "_")
            CircuitBreakerState.objects.update_or_create(
                provider_name=self.provider,
                defaults={
                    "state": state_str,
                    "failure_count": cb.fail_counter,
                },
            )
        except Exception as e:
            logger.error(f"Failed to persist circuit breaker state: {e}")

    def failure(self, cb, exc):
        logger.warning(f"[CircuitBreaker] {self.provider} failure: {exc}")
        try:
            CircuitBreakerState.objects.update_or_create(
                provider_name=self.provider,
                defaults={
                    "failure_count": cb.fail_counter,
                    "last_failure_at": timezone.now(),
                },
            )
        except Exception as e:
            logger.error(f"Failed to persist failure: {e}")

    def success(self, cb):
        try:
            CircuitBreakerState.objects.update_or_create(
                provider_name=self.provider,
                defaults={
                    "failure_count": cb.fail_counter,
                },
            )
        except Exception:
            pass


def _make_breaker(provider: str) -> pybreaker.CircuitBreaker:
    fail_max = getattr(settings, "CIRCUIT_BREAKER_FAIL_MAX", 3)
    reset_timeout = getattr(settings, "CIRCUIT_BREAKER_RESET_TIMEOUT", 30)
    return pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        listeners=[_DBStateListener(provider)],
        name=f"{provider}_breaker",
    )


# Module-level circuit breakers (singletons)
_aldeamo_breaker: pybreaker.CircuitBreaker = None
_twilio_breaker: pybreaker.CircuitBreaker = None


def _get_aldeamo_breaker() -> pybreaker.CircuitBreaker:
    global _aldeamo_breaker
    if _aldeamo_breaker is None:
        _aldeamo_breaker = _make_breaker(SmsProvider.ALDEAMO)
    return _aldeamo_breaker


def _get_twilio_breaker() -> pybreaker.CircuitBreaker:
    global _twilio_breaker
    if _twilio_breaker is None:
        _twilio_breaker = _make_breaker(SmsProvider.TWILIO)
    return _twilio_breaker


def reset_breakers():
    """Reset both circuit breakers (for testing)."""
    global _aldeamo_breaker, _twilio_breaker
    _aldeamo_breaker = None
    _twilio_breaker = None


# ── Gateway public interface ──────────────────────────────────────────────────

def send_otp_sms(phone_number: str, message: str) -> Tuple[str, dict]:
    """
    Send an SMS via the primary provider (Aldeamo) with automatic fallback to Twilio via HTTP.
    """
    aldeamo_breaker = _get_aldeamo_breaker()
    twilio_breaker = _get_twilio_breaker()

    aldeamo_url = getattr(settings, "ALDEAMO_SERVICE_URL", "http://localhost:8001/send")
    twilio_url = getattr(settings, "TWILIO_SERVICE_URL", "http://localhost:8002/send")
    payload = {"phone_number": phone_number, "message": message}

    # ── Try Aldeamo (primary) ─────────────────────────────────────────────────
    if not _aldeamo_semaphore.acquire(timeout=2):
        logger.warning("[Bulkhead] Aldeamo semaphore timeout — too many concurrent requests")
    else:
        try:
            @aldeamo_breaker
            def call_aldeamo():
                resp = requests.post(aldeamo_url, json=payload, timeout=5)
                resp.raise_for_status()
                return resp.json()

            result = call_aldeamo()
            _ensure_cb_state(SmsProvider.ALDEAMO)
            return SmsProvider.ALDEAMO, result
        except pybreaker.CircuitBreakerError:
            logger.warning("[CircuitBreaker] Aldeamo circuit OPEN — falling back to Twilio")
        except requests.exceptions.RequestException as e:
            logger.warning(f"[Aldeamo] API error: {e} — falling back to Twilio")
        except Exception as e:
            logger.warning(f"[Aldeamo] Unexpected error: {e} — falling back to Twilio")
        finally:
            _aldeamo_semaphore.release()

    # ── Fall back to Twilio ───────────────────────────────────────────────────
    if not _twilio_semaphore.acquire(timeout=2):
        raise RuntimeError("Twilio bulkhead exhausted — too many concurrent requests")

    try:
        @twilio_breaker
        def call_twilio():
            resp = requests.post(twilio_url, json=payload, timeout=5)
            resp.raise_for_status()
            return resp.json()

        result = call_twilio()
        _ensure_cb_state(SmsProvider.TWILIO)
        return SmsProvider.TWILIO, result
    except pybreaker.CircuitBreakerError:
        raise RuntimeError("Twilio circuit breaker is OPEN — both providers unavailable")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Twilio API error: {e}")
    finally:
        _twilio_semaphore.release()


def _cb_state_name(breaker) -> str:
    """Get state name from a pybreaker CircuitBreaker (handles both str and object)."""
    if breaker is None:
        return "CLOSED"
    state = breaker.current_state
    # pybreaker 1.x: current_state is a string like 'closed', 'open', 'half-open'
    if isinstance(state, str):
        return state.upper().replace("-", "_")
    # Older pybreaker: current_state is an object with a .name attribute
    return state.name.upper()


def get_circuit_breaker_status() -> dict:
    """Return current state of both circuit breakers."""
    aldeamo_breaker = _get_aldeamo_breaker()
    twilio_breaker = _get_twilio_breaker()

    return {
        SmsProvider.ALDEAMO: {
            "state": _cb_state_name(aldeamo_breaker),
            "failure_count": aldeamo_breaker.fail_counter if aldeamo_breaker else 0,
            "fail_max": aldeamo_breaker.fail_max if aldeamo_breaker else 3,
        },
        SmsProvider.TWILIO: {
            "state": _cb_state_name(twilio_breaker),
            "failure_count": twilio_breaker.fail_counter if twilio_breaker else 0,
            "fail_max": twilio_breaker.fail_max if twilio_breaker else 3,
        },
    }


def _ensure_cb_state(provider: str):
    """Ensure a CircuitBreakerState DB record exists for this provider."""
    try:
        CircuitBreakerState.objects.get_or_create(
            provider_name=provider,
            defaults={"state": CircuitBreakerState.CLOSED, "failure_count": 0},
        )
    except Exception:
        pass
