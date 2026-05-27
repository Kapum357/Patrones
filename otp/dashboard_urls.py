from django.urls import path
from .dashboard_views import dashboard

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("", dashboard, name="dashboard-root"),
]
