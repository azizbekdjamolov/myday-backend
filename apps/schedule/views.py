from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import ClassSchedule
from .serializers import ClassScheduleSerializer


class ClassScheduleViewSet(viewsets.ModelViewSet):
    """CRUD for the authenticated user's class schedule only."""

    serializer_class = ClassScheduleSerializer

    def get_queryset(self):
        return ClassSchedule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)