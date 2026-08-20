from __future__ import annotations

from rest_framework import viewsets

from apps.permissions.permissions import HasInternlikAccess

from .models import InternlikEntry
from .serializers import InternlikEntrySerializer


class InternlikEntryViewSet(viewsets.ModelViewSet):
    """Internlik records — strictly limited to authorized users."""

    permission_classes = [HasInternlikAccess]
    serializer_class = InternlikEntrySerializer

    def get_queryset(self):
        return InternlikEntry.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)