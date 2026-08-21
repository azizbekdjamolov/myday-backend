from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BullDropAccountViewSet

router = DefaultRouter()
router.register("accounts", BullDropAccountViewSet, basename="bulldrop-account")

urlpatterns = [path("", include(router.urls))]
