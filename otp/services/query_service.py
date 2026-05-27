"""
OTP Query Service — handles the read side of CQRS.

Reads exclusively from MongoDB (otp_notification_view collection).
This is the denormalized, read-optimized projection of OTP events.

If MongoDB is unavailable, falls back to reading directly from SQL
(OtpRequest model) with a warning.
"""
import logging
from typing import List, Optional

from otp.mongo import get_otp_collection, is_mongo_available

logger = logging.getLogger(__name__)


def _serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to a JSON-serializable dict."""
    if doc is None:
        return None
    result = {k: v for k, v in doc.items() if k != "_id"}
    if "_id" in doc:
        result["_mongo_id"] = str(doc["_id"])
    return result


def get_otp_by_id(otp_id: str) -> Optional[dict]:
    """
    Query: Get a single OTP notification view by its ID.
    Reads from MongoDB read model.
    """
    if not is_mongo_available():
        return _fallback_get_by_id(otp_id)

    collection = get_otp_collection()
    doc = collection.find_one({"otp_id": otp_id})
    return _serialize_doc(doc)


def list_all_otps(limit: int = 50, phone_number: str = None) -> List[dict]:
    """
    Query: List OTP notification views, optionally filtered by phone.
    Reads from MongoDB read model.
    """
    if not is_mongo_available():
        return _fallback_list_all(limit=limit, phone_number=phone_number)

    collection = get_otp_collection()
    query = {}
    if phone_number:
        query["phone_number"] = phone_number

    cursor = collection.find(query).sort("created_at", -1).limit(limit)
    return [_serialize_doc(doc) for doc in cursor]


def get_outbox_stats() -> dict:
    """Return aggregate stats about the Outbox events."""
    from otp.models import OutboxEvent
    total = OutboxEvent.objects.count()
    projected = OutboxEvent.objects.filter(projected=True).count()
    pending = total - projected
    return {
        "total": total,
        "projected": projected,
        "pending": pending,
    }


# ── SQL fallbacks (when MongoDB is unavailable) ───────────────────────────────

def _fallback_get_by_id(otp_id: str) -> Optional[dict]:
    """Fallback: read from SQL OtpRequest."""
    logger.warning("[QueryService] MongoDB unavailable — reading from SQL fallback")
    from otp.models import OtpRequest
    try:
        req = OtpRequest.objects.get(id=otp_id)
        return _sql_to_view(req)
    except OtpRequest.DoesNotExist:
        return None


def _fallback_list_all(limit: int = 50, phone_number: str = None) -> List[dict]:
    """Fallback: read from SQL OtpRequest."""
    logger.warning("[QueryService] MongoDB unavailable — reading from SQL fallback")
    from otp.models import OtpRequest
    qs = OtpRequest.objects.all()
    if phone_number:
        qs = qs.filter(phone_number=phone_number)
    return [_sql_to_view(r) for r in qs[:limit]]


def _sql_to_view(req) -> dict:
    return {
        "otp_id": str(req.id),
        "phone_number": req.phone_number,
        "otp_code": req.otp_code,
        "status": req.status,
        "provider_used": req.provider_used,
        "error_message": req.error_message,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "source": "SQL_FALLBACK",
    }
