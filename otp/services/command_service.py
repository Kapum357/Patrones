"""
OTP Command Service — handles the write side of CQRS (ASYNCHRONOUS).

Responsibilities:
  1. Generate a 6-digit OTP code
  2. Persist OtpRequest to SQL (status=PENDING)
  3. Write OTP_CREATED OutboxEvent atomically
  4. Return IMMEDIATELY — SMS is sent asynchronously by the SMS Worker

The SMS Worker (sms_worker.py) picks up PENDING requests and routes them
through the SMS Gateway (Circuit Breaker + Bulkhead).
"""
import logging
import random
import string
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from otp.models import OtpRequest, OutboxEvent, OtpStatus

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5


def _generate_otp(length: int = 6) -> str:
    """Generate a cryptographically safe numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


def send_otp(phone_number: str) -> dict:
    """
    Command: Enqueue an OTP for the given phone number.

    The OTP is persisted with status=PENDING and will be processed
    asynchronously by the SMS Worker. Returns immediately.

    Returns a dict describing the queued request:
    {
        "otp_id": str,
        "phone_number": str,
        "status": "PENDING",
        "otp_code": str,   # included for demo purposes only
        "created_at": str,
    }
    """
    otp_code = _generate_otp()
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    # ── Persist command + Outbox event atomically ────────────────────────────
    with transaction.atomic():
        otp_request = OtpRequest.objects.create(
            phone_number=phone_number,
            otp_code=otp_code,
            status=OtpStatus.PENDING,
            expires_at=expires_at,
        )
        OutboxEvent.objects.create(
            event_type="OTP_CREATED",
            payload={
                "otp_id": str(otp_request.id),
                "phone_number": phone_number,
                "otp_code": otp_code,
                "status": OtpStatus.PENDING,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )

    logger.info(
        f"[CommandService] OTP enqueued: {otp_request.id} for {phone_number} "
        f"(async — will be processed by SMS Worker)"
    )

    return {
        "otp_id": str(otp_request.id),
        "phone_number": phone_number,
        "status": OtpStatus.PENDING,
        "otp_code": otp_code,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
