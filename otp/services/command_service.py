"""
OTP Command Service — handles the write side of CQRS.

Responsibilities:
  1. Generate a 6-digit OTP code
  2. Persist OtpRequest to SQL (status=PENDING)
  3. Write OTP_CREATED OutboxEvent atomically
  4. Route through SMS Gateway (Circuit Breaker + Bulkhead)
  5. Update OtpRequest status (SENT / FAILED)
  6. Write OTP_SENT / OTP_FAILED OutboxEvent
  7. Return result to caller

All SQL writes within a single step are atomic (not across the whole flow,
since the SMS call is an external side-effect).
"""
import logging
import random
import string
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from otp.models import OtpRequest, OutboxEvent, OtpStatus, SmsProvider
from otp.services.sms_gateway import send_otp_sms

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5


def _generate_otp(length: int = 6) -> str:
    """Generate a cryptographically safe numeric OTP."""
    return "".join(random.choices(string.digits, k=length))


def send_otp(phone_number: str) -> dict:
    """
    Command: Send an OTP to the given phone number.

    Returns a dict describing the outcome:
    {
        "otp_id": str,
        "phone_number": str,
        "status": "SENT" | "FAILED",
        "provider": str | None,
        "otp_code": str,   # included for demo purposes only
        "created_at": str,
    }
    """
    otp_code = _generate_otp()
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)

    # ── Step 1: Persist command + initial Outbox event (atomic) ──────────────
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

    logger.info(f"[CommandService] OTP created: {otp_request.id} for {phone_number}")

    # ── Step 2: Send via SMS Gateway (external call, outside transaction) ─────
    provider_used = None
    error_message = None
    try:
        message = f"Tu código OTP es: {otp_code}. Válido por {OTP_TTL_MINUTES} minutos."
        provider_used, sms_result = send_otp_sms(phone_number, message)
        new_status = OtpStatus.SENT
        logger.info(
            f"[CommandService] SMS sent via {provider_used}: {sms_result}"
        )
    except Exception as exc:
        new_status = OtpStatus.FAILED
        error_message = str(exc)
        logger.error(f"[CommandService] SMS failed for {otp_request.id}: {exc}")

    # ── Step 3: Update OtpRequest + write final Outbox event (atomic) ─────────
    event_type = "OTP_SENT" if new_status == OtpStatus.SENT else "OTP_FAILED"
    with transaction.atomic():
        otp_request.status = new_status
        otp_request.provider_used = provider_used
        otp_request.error_message = error_message
        otp_request.save(update_fields=["status", "provider_used", "error_message"])

        OutboxEvent.objects.create(
            event_type=event_type,
            payload={
                "otp_id": str(otp_request.id),
                "phone_number": phone_number,
                "otp_code": otp_code,
                "status": new_status,
                "provider_used": provider_used,
                "error_message": error_message,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "sent_at": timezone.now().isoformat() if new_status == OtpStatus.SENT else None,
            },
        )

    return {
        "otp_id": str(otp_request.id),
        "phone_number": phone_number,
        "status": new_status,
        "provider": provider_used,
        "otp_code": otp_code,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
