from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("otp.urls")),
    path("", include("otp.dashboard_urls")),
]
