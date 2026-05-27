from django.contrib import admin
from .models import OtpRequest, OutboxEvent, CircuitBreakerState


@admin.register(OtpRequest)
class OtpRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "phone_number", "otp_code", "status", "provider_used", "created_at")
    list_filter = ("status", "provider_used")
    search_fields = ("phone_number",)
    readonly_fields = ("id", "created_at")


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "projected", "created_at", "projected_at")
    list_filter = ("event_type", "projected")
    readonly_fields = ("id", "created_at")


@admin.register(CircuitBreakerState)
class CircuitBreakerStateAdmin(admin.ModelAdmin):
    list_display = ("provider_name", "state", "failure_count", "last_failure_at", "updated_at")
    readonly_fields = ("updated_at",)
