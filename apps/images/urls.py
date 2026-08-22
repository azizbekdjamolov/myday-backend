from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ImageViewSet

router = DefaultRouter()
router.register("", ImageViewSet, basename="image")

urlpatterns = [
    path("", include(router.urls)),
]
