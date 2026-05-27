from django.urls import path
from . import views

app_name = "otp"

urlpatterns = [
    # Auth
    path("auth/token/", views.get_token, name="get-token"),

    # OTP Commands (write side)
    path("otp/send/", views.send_otp, name="send-otp"),

    # OTP Queries (read side — reads from MongoDB)
    path("otp/", views.list_otps, name="list-otps"),
    path("otp/<str:otp_id>/", views.get_otp, name="get-otp"),

    # System / Observability
    path("system/circuit-breaker/", views.circuit_breaker_status, name="circuit-breaker"),
    path("system/provider-stats/", views.provider_stats, name="provider-stats"),
    path("system/outbox/", views.outbox_stats, name="outbox-stats"),
    path("health/", views.health_check, name="health"),
]
