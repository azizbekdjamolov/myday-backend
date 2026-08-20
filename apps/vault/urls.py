from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import VaultFileViewSet, VaultItemViewSet, VaultPasswordView, VaultStatusView

router = DefaultRouter()
router.register("items", VaultItemViewSet, basename="vault-item")
router.register("files", VaultFileViewSet, basename="vault-file")

urlpatterns = [
    path("", include(router.urls)),
    path("status", VaultStatusView.as_view(), name="vault-status"),
    path("password", VaultPasswordView.as_view(), name="vault-password"),
]