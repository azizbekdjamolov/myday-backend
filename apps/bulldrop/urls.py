from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BullDropAccountViewSet, BullDropClaimViewSet

router = DefaultRouter()
router.register("accounts", BullDropAccountViewSet, basename="bulldrop-account")
router.register("claims", BullDropClaimViewSet, basename="bulldrop-claim")

urlpatterns = [path("", include(router.urls))]