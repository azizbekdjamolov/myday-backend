"""Dashboard aggregate endpoint.

Answers the single question the app exists for: "What do I have today?" —
today's/next class with time remaining, upcoming reminders, and — only for
permitted users — BullDrop and Internlik summaries. Unpermitted modules are
absent from the response entirely.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bulldrop.models import BullDropAccount
from apps.internlik.models import InternlikEntry
from apps.reminders.models import Reminder
from apps.schedule.services import next_class_for_user


def greeting_for(hour: int) -> str:
    if hour < 5:
        return "Good night"
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()

        # Upcoming reminders: future occurrences, plus past occurrences of
        # recurring reminders (they are due until completed).
        upcoming = (
            Reminder.objects.filter(
                user=user,
                completed=False,
            )
            .filter(Q(remind_at__gte=now) | Q(recurrence__in=("daily", "weekly", "custom")))
            .order_by("remind_at")[:6]
        )

        payload = {
            "greeting": greeting_for(now.hour),
            "today": now.date().isoformat(),
            "next_class": next_class_for_user(user, now),
            "reminders": [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "next_at": r.next_remind_at(now).isoformat(),
                    "recurrence": r.recurrence,
                }
                for r in upcoming
            ],
        }

        if user.is_superuser or user.has_bulldrop_access:
            accounts = list(BullDropAccount.objects.filter(user=user))
            ready = sum(1 for a in accounts if a.status == "ready")
            payload["bulldrop"] = {"has_access": True, "ready": ready, "waiting": len(accounts) - ready}

        if user.is_superuser or user.has_internlik_access:
            payload["internlik"] = {
                "has_access": True,
                "active": InternlikEntry.objects.filter(user=user).count(),
            }

        return Response(payload)