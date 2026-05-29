import uuid
from django.db import models


class OtpStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class SmsProvider(models.TextChoices):
    ALDEAMO = "ALDEAMO", "Aldeamo"
    TWILIO = "TWILIO", "Twilio"


class OtpRequest(models.Model):
    """
    Command-side entity: represents one OTP send request.
    Written by the Command Service, read via projections.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=20)
    otp_code = models.CharField(max_length=6)
    status = models.CharField(
        max_length=10,
        choices=OtpStatus.choices,
        default=OtpStatus.PENDING,
    )
    provider_used = models.CharField(
        max_length=10,
        choices=SmsProvider.choices,
        null=True,
        blank=True,
    )
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "OTP Request"
        verbose_name_plural = "OTP Requests"

    def __str__(self):
        return f"OTP[{self.phone_number}] → {self.status} via {self.provider_used or 'N/A'}"


class OutboxEvent(models.Model):
    """
    Outbox pattern: events written atomically with the OTP request.
    The Projector polls this table and projects events to MongoDB.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=50)  # OTP_CREATED, OTP_SENT, OTP_FAILED
    payload = models.JSONField()  # Full denormalized event data
    created_at = models.DateTimeField(auto_now_add=True)
    projected = models.BooleanField(default=False)
    projected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Outbox Event"
        verbose_name_plural = "Outbox Events"
        indexes = [
            models.Index(fields=["projected", "created_at"]),
        ]

    def __str__(self):
        status = "✓" if self.projected else "⏳"
        return f"{status} {self.event_type} @ {self.created_at:%Y-%m-%d %H:%M:%S}"


class CircuitBreakerState(models.Model):
    """
    Persisted Circuit Breaker state for each SMS provider.
    Updated by the SMS Gateway whenever the circuit transitions.
    """
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"
    STATE_CHOICES = [
        (CLOSED, "Closed — Normal operation"),
        (OPEN, "Open — Provider failing, requests rejected"),
        (HALF_OPEN, "Half-Open — Testing recovery"),
    ]

    provider_name = models.CharField(
        max_length=10,
        choices=SmsProvider.choices,
        unique=True,
    )
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=CLOSED)
    failure_count = models.IntegerField(default=0)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Circuit Breaker State"
        verbose_name_plural = "Circuit Breaker States"

    def __str__(self):
        return f"{self.provider_name}: {self.state} ({self.failure_count} failures)"
