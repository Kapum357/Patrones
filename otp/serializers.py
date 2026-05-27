from rest_framework import serializers
from .models import OtpRequest, OutboxEvent, CircuitBreakerState


class OtpRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = OtpRequest
        fields = [
            "id", "phone_number", "otp_code", "status",
            "provider_used", "error_message", "created_at", "expires_at",
        ]
        read_only_fields = fields


class OutboxEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutboxEvent
        fields = [
            "id", "event_type", "payload", "created_at",
            "projected", "projected_at",
        ]
        read_only_fields = fields


class CircuitBreakerStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CircuitBreakerState
        fields = [
            "provider_name", "state", "failure_count",
            "last_failure_at", "updated_at",
        ]
        read_only_fields = fields


class SendOtpRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(
        max_length=20,
        help_text="E.164 phone number, e.g. +573001234567",
    )

    def validate_phone_number(self, value):
        import re
        # Accept + followed by digits, or plain digits
        if not re.match(r"^\+?\d{7,15}$", value):
            raise serializers.ValidationError(
                "Invalid phone number. Use E.164 format, e.g. +573001234567"
            )
        return value


class TokenRequestSerializer(serializers.Serializer):
    client_id = serializers.CharField()
    client_secret = serializers.CharField()
