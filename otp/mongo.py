"""
MongoDB connection helper — singleton client for the read-side projection store.
"""
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from django.conf import settings

logger = logging.getLogger(__name__)

_client = None
_db = None


def get_mongo_client() -> MongoClient:
    """Return a singleton MongoDB client."""
    global _client
    if _client is None:
        uri = getattr(settings, "MONGODB_URI", "mongodb://localhost:27017")
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return _client


def get_mongo_db():
    """Return the MongoDB database for OTP read projections."""
    global _db
    if _db is None:
        client = get_mongo_client()
        db_name = getattr(settings, "MONGODB_DB_NAME", "otp_cqrs")
        _db = client[db_name]
    return _db


def get_otp_collection():
    """Return the OtpNotificationView collection."""
    db = get_mongo_db()
    return db["otp_notification_view"]


def is_mongo_available() -> bool:
    """Check if MongoDB is reachable."""
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return True
    except (ConnectionFailure, Exception) as e:
        logger.warning(f"MongoDB not available: {e}")
        return False
