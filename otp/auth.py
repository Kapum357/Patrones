"""
JWT-based Authorization Service.

Flow:
  1. Client POSTs {client_id, client_secret} to /api/auth/token/
  2. Server validates credentials against JWT_CLIENTS setting
  3. Server returns signed JWT with {client_id, exp}
  4. Client includes token in Authorization: Bearer <token> header
  5. JWTAuthentication class validates token on protected endpoints
"""
import logging
import time

import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


def get_jwt_secret() -> str:
    return getattr(settings, "JWT_SECRET_KEY", "change-me-in-production")


def get_jwt_expiry() -> int:
    return getattr(settings, "JWT_EXPIRY_SECONDS", 3600)


def generate_token(client_id: str) -> str:
    """
    Generate a signed JWT for the given client_id.
    """
    payload = {
        "client_id": client_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + get_jwt_expiry(),
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm="HS256")
    return token


def validate_token(token: str) -> dict:
    """
    Decode and validate a JWT. Returns the payload dict.
    Raises AuthenticationFailed on invalid/expired tokens.
    """
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Token has expired.")
    except jwt.InvalidTokenError as e:
        raise AuthenticationFailed(f"Invalid token: {e}")


def validate_client_credentials(client_id: str, client_secret: str) -> bool:
    """
    Check client_id + client_secret against the configured clients.
    """
    clients = getattr(settings, "JWT_CLIENTS", {})
    expected_secret = clients.get(client_id)
    if expected_secret is None:
        return False
    return expected_secret == client_secret


class _AuthenticatedClient:
    """Minimal user-like object for DRF compatibility."""
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.is_authenticated = True

    def __str__(self):
        return f"Client({self.client_id})"


class JWTAuthentication(BaseAuthentication):
    """
    DRF authentication class.
    Reads the token from: Authorization: Bearer <token>
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None  # No token — let DRF handle unauthenticated case

        token = auth_header[len("Bearer "):]
        payload = validate_token(token)
        client = _AuthenticatedClient(payload["client_id"])
        return (client, token)

    def authenticate_header(self, request):
        return "Bearer"
