"""Per-app API routing.

Keeps versioned URLs composed in one place so a new version bump is a single
change.
"""

from django.urls import include, path

urlpatterns = [
    path("auth/", include("apps.accounts.urls")),
    path("vault/", include("apps.vault.urls")),
    path("bulldrop/", include("apps.bulldrop.urls")),
    path("internlik/", include("apps.internlik.urls")),
    path("schedule/", include("apps.schedule.urls")),
    path("reminders/", include("apps.reminders.urls")),
    path("admin/", include("apps.adminpanel.urls")),
    path("", include("apps.dashboard.urls")),
]