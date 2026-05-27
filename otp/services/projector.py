"""
Outbox Projector — reads unprojected OutboxEvent rows from SQL
and upserts them into the MongoDB otp_notification_view collection.

Pattern: Polling-based event projection
  ┌──────────────────────────────────────────────────────┐
  │  Projector polls every N seconds                     │
  │                                                      │
  │  SELECT * FROM outbox_event                          │
  │  WHERE projected = false ORDER BY created_at         │
  │       │                                              │
  │       ▼                                              │
  │  For each event:                                     │
  │    1. Upsert into MongoDB otp_notification_view      │
  │    2. Mark OutboxEvent.projected = True              │
  │                                                      │
  └──────────────────────────────────────────────────────┘
"""
import logging
from typing import List

from django.utils import timezone

from otp.models import OutboxEvent
from otp.mongo import get_otp_collection, is_mongo_available

logger = logging.getLogger(__name__)


def project_pending_events(batch_size: int = 100) -> int:
    """
    Project all unprojected OutboxEvents to MongoDB.

    Returns the number of events successfully projected.
    """
    if not is_mongo_available():
        logger.warning("[Projector] MongoDB not available — skipping projection cycle")
        return 0

    pending_events: List[OutboxEvent] = list(
        OutboxEvent.objects.filter(projected=False)
        .order_by("created_at")[:batch_size]
    )

    if not pending_events:
        return 0

    collection = get_otp_collection()
    projected_count = 0

    for event in pending_events:
        try:
            _project_event(collection, event)
            event.projected = True
            event.projected_at = timezone.now()
            event.save(update_fields=["projected", "projected_at"])
            projected_count += 1
        except Exception as exc:
            logger.error(f"[Projector] Failed to project event {event.id}: {exc}")
            # Continue with next event — don't let one failure block others

    if projected_count > 0:
        logger.info(f"[Projector] Projected {projected_count}/{len(pending_events)} events")

    return projected_count


def _project_event(collection, event: OutboxEvent):
    """
    Upsert an OtpNotificationView document in MongoDB based on the event type.

    OTP_CREATED → Insert/init the document
    OTP_SENT    → Update status, provider, sent_at
    OTP_FAILED  → Update status, error_message
    """
    payload = event.payload
    otp_id = payload.get("otp_id")

    if not otp_id:
        logger.warning(f"[Projector] Event {event.id} has no otp_id in payload")
        return

    if event.event_type == "OTP_CREATED":
        document = {
            "otp_id": otp_id,
            "phone_number": payload.get("phone_number"),
            "otp_code": payload.get("otp_code"),
            "status": payload.get("status", "PENDING"),
            "provider_used": None,
            "error_message": None,
            "created_at": payload.get("created_at"),
            "expires_at": payload.get("expires_at"),
            "sent_at": None,
            "last_event": "OTP_CREATED",
            "event_history": [event.event_type],
        }
        collection.update_one(
            {"otp_id": otp_id},
            {"$setOnInsert": document},
            upsert=True,
        )

    elif event.event_type == "OTP_SENT":
        collection.update_one(
            {"otp_id": otp_id},
            {
                "$set": {
                    "status": "SENT",
                    "provider_used": payload.get("provider_used"),
                    "sent_at": payload.get("sent_at"),
                    "last_event": "OTP_SENT",
                },
                "$push": {"event_history": "OTP_SENT"},
            },
            upsert=True,
        )

    elif event.event_type == "OTP_FAILED":
        collection.update_one(
            {"otp_id": otp_id},
            {
                "$set": {
                    "status": "FAILED",
                    "error_message": payload.get("error_message"),
                    "last_event": "OTP_FAILED",
                },
                "$push": {"event_history": "OTP_FAILED"},
            },
            upsert=True,
        )

    else:
        logger.warning(f"[Projector] Unknown event type: {event.event_type}")
