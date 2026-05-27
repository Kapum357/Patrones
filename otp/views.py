"""
OTP API Views — Command and Query endpoints.

Endpoints:
  POST /api/auth/token/          → Get JWT token
  POST /api/otp/send/            → Send OTP (command)
  GET  /api/otp/                 → List OTPs (query, reads MongoDB)
  GET  /api/otp/<id>/            → Get OTP by ID (query, reads MongoDB)
  GET  /api/system/circuit-breaker/  → Circuit Breaker status
  GET  /api/system/outbox/           → Outbox stats
"""
import logging

from django.db.models import Count, Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .auth import validate_client_credentials, generate_token
from .models import CircuitBreakerState, OutboxEvent, OtpRequest
from .serializers import (
    SendOtpRequestSerializer,
    TokenRequestSerializer,
    CircuitBreakerStateSerializer,
    OutboxEventSerializer,
)
from .services import command_service, query_service
from .services.sms_gateway import get_circuit_breaker_status

logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def get_token(request):
    """
    POST /api/auth/token/
    Body: { "client_id": "app_web", "client_secret": "secret_web_123" }
    Returns: { "access_token": "...", "token_type": "Bearer", "expires_in": 3600 }
    """
    serializer = TokenRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    client_id = serializer.validated_data["client_id"]
    client_secret = serializer.validated_data["client_secret"]

    if not validate_client_credentials(client_id, client_secret):
        return Response(
            {"error": "Invalid client credentials"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    from django.conf import settings
    token = generate_token(client_id)
    return Response({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": getattr(settings, "JWT_EXPIRY_SECONDS", 3600),
        "client_id": client_id,
    })


# ── OTP Commands ──────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_otp(request):
    """
    POST /api/otp/send/
    Header: Authorization: Bearer <token>
    Body: { "phone_number": "+573001234567" }

    Triggers the OTP Command Service:
      1. Generates OTP
      2. Writes to SQL + Outbox
      3. Sends via SMS Gateway (Circuit Breaker + Bulkhead)
      4. Returns result
    """
    serializer = SendOtpRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    phone_number = serializer.validated_data["phone_number"]

    try:
        result = command_service.send_otp(phone_number)
        http_status = status.HTTP_201_CREATED if result["status"] == "SENT" else status.HTTP_207_MULTI_STATUS
        return Response(result, status=http_status)
    except Exception as exc:
        logger.exception(f"Unexpected error in send_otp: {exc}")
        return Response(
            {"error": "Internal server error", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ── OTP Queries ───────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_otps(request):
    """
    GET /api/otp/?phone_number=+573001234567
    Reads from MongoDB read model (OtpNotificationView).
    """
    phone_number = request.query_params.get("phone_number")
    limit = int(request.query_params.get("limit", 50))

    from .mongo import is_mongo_available
    mongo_ok = is_mongo_available()
    results = query_service.list_all_otps(limit=limit, phone_number=phone_number)
    return Response({
        "count": len(results),
        "results": results,
        "source": "mongodb_read_model" if mongo_ok else "sql_fallback",
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_otp(request, otp_id):
    """
    GET /api/otp/<otp_id>/
    Reads from MongoDB read model (OtpNotificationView).
    """
    result = query_service.get_otp_by_id(str(otp_id))
    if result is None:
        return Response({"error": "OTP not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(result)


# ── System / Observability ────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def circuit_breaker_status(request):
    """
    GET /api/system/circuit-breaker/
    Returns live Circuit Breaker state for Aldeamo and Twilio.
    """
    # Live state from pybreaker
    live_state = get_circuit_breaker_status()

    # Persisted state from DB (for history / dashboard)
    db_states = CircuitBreakerState.objects.all()
    db_serializer = CircuitBreakerStateSerializer(db_states, many=True)

    return Response({
        "live": live_state,
        "persisted": db_serializer.data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def outbox_stats(request):
    """
    GET /api/system/outbox/
    Returns Outbox statistics and recent events.
    """
    stats = query_service.get_outbox_stats()
    recent_events = OutboxEvent.objects.order_by("-created_at")[:20]
    serializer = OutboxEventSerializer(recent_events, many=True)

    return Response({
        "stats": stats,
        "recent_events": serializer.data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def provider_stats(request):
    """
    GET /api/system/provider-stats/
    Returns real-time statistics for SMS providers based on OtpRequest table.
    """
    stats = OtpRequest.objects.values('provider_used').annotate(
        total=Count('id'),
        sent=Count('id', filter=Q(status='SENT')),
        failed=Count('id', filter=Q(status='FAILED'))
    )
    
    result = {
        "ALDEAMO": {"total": 0, "sent": 0, "failed": 0, "success_rate": 0.0},
        "TWILIO": {"total": 0, "sent": 0, "failed": 0, "success_rate": 0.0},
    }
    
    for stat in stats:
        provider = stat['provider_used']
        if provider in result:
            result[provider]['total'] = stat['total']
            result[provider]['sent'] = stat['sent']
            result[provider]['failed'] = stat['failed']
            if stat['total'] > 0:
                result[provider]['success_rate'] = round((stat['sent'] / stat['total']) * 100, 1)
                
    return Response(result)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """GET /api/health/ — Basic health check."""
    from .mongo import is_mongo_available
    mongo_ok = is_mongo_available()
    return Response({
        "status": "ok",
        "mongodb": "connected" if mongo_ok else "unavailable",
    })
