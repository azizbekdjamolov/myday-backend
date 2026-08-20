"""Root URL configuration."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("apps.api_urls")),
]

# Basic health check for load balancers / uptime probes.
urlpatterns.append(
    path(
        "healthz/",
        lambda request: JsonResponse({"status": "ok", "app": "myday"}),
    )
)