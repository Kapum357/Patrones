"""
Dashboard view — serves the HTML monitoring dashboard.
"""
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


def dashboard(request):
    """Main monitoring dashboard."""
    return render(request, "dashboard.html")
