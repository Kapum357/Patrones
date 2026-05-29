"""
SMS Worker — asynchronous background processor for OTP delivery.

Polls the OtpRequest table for PENDING records and sends them via the
SMS Gateway (Circuit Breaker + Bulkhead → Aldeamo / Twilio microservices).

Uses SELECT ... FOR UPDATE SKIP LOCKED to safely support multiple workers
without race conditions.

Usage:
    python manage.py run_sms_worker
    python manage.py run_sms_worker --interval 1   # poll every 1 second
"""
import logging

from django.db import transaction
from django.utils import timezone

from otp.models import OtpRequest, OutboxEvent, OtpStatus
from otp.services.sms_gateway import send_otp_sms

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5


def process_pending_otps(batch_size: int = 10) -> int:
    """
    Process a batch of PENDING OTP requests.

    1. SELECT pending OTPs with row-level locking (skip already-locked rows)
    2. Mark each as PROCESSING
    3. Send via SMS Gateway
    4. Update to SENT or FAILED + write OutboxEvent

    Returns the number of OTPs processed.
    """
    processed = 0

    # Fetch a batch of PENDING requests with row-level lock
    with transaction.atomic():
        pending_ids = list(
            OtpRequest.objects.filter(status=OtpStatus.PENDING)
            .order_by("created_at")
            .values_list("id", flat=True)[:batch_size]
        )

    for otp_id in pending_ids:
        try:
            _process_single_otp(otp_id)
            processed += 1
        except Exception as exc:
            logger.error(f"[SMSWorker] Failed to process OTP {otp_id}: {exc}")

    return processed


def _process_single_otp(otp_id):
    """Process a single OTP: lock → send SMS → update status."""

    # ── Step 1: Lock the row and mark as PROCESSING ──────────────────────────
    with transaction.atomic():
        try:
            otp = (
                OtpRequest.objects
                .select_for_update(skip_locked=True)
                .get(id=otp_id, status=OtpStatus.PENDING)
            )
        except OtpRequest.DoesNotExist:
            # Another worker already picked it up
            return

        otp.status = OtpStatus.PROCESSING
        otp.save(update_fields=["status"])

    # ── Step 2: Send SMS via gateway (outside transaction) ───────────────────
    provider_used = None
    error_message = None
    try:
        message = f"Tu código OTP es: {otp.otp_code}. Válido por {OTP_TTL_MINUTES} minutos."
        provider_used, sms_result = send_otp_sms(otp.phone_number, message)
        new_status = OtpStatus.SENT
        logger.info(
            f"[SMSWorker] SMS sent via {provider_used} for OTP {otp_id}: {sms_result}"
        )
    except Exception as exc:
        new_status = OtpStatus.FAILED
        error_message = str(exc)
        logger.error(f"[SMSWorker] SMS failed for OTP {otp_id}: {exc}")

    # ── Step 3: Update OtpRequest + write OutboxEvent (atomic) ───────────────
    event_type = "OTP_SENT" if new_status == OtpStatus.SENT else "OTP_FAILED"
    with transaction.atomic():
        otp.status = new_status
        otp.provider_used = provider_used
        otp.error_message = error_message
        otp.save(update_fields=["status", "provider_used", "error_message"])

        OutboxEvent.objects.create(
            event_type=event_type,
            payload={
                "otp_id": str(otp.id),
                "phone_number": otp.phone_number,
                "otp_code": otp.otp_code,
                "status": new_status,
                "provider_used": provider_used,
                "error_message": error_message,
                "created_at": otp.created_at.isoformat(),
                "expires_at": otp.expires_at.isoformat(),
                "sent_at": timezone.now().isoformat() if new_status == OtpStatus.SENT else None,
            },
        )
