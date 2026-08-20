from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import InternlikEntryViewSet

router = DefaultRouter()
router.register("entries", InternlikEntryViewSet, basename="internlik-entry")

urlpatterns = [path("", include(router.urls))]