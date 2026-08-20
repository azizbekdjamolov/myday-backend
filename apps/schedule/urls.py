from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClassScheduleViewSet

router = DefaultRouter()
router.register("classes", ClassScheduleViewSet, basename="class")

urlpatterns = [path("", include(router.urls))]