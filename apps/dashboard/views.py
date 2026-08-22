"""Dashboard aggregate endpoint.

Answers the single question the app exists for: "What do I have today?" —
today's/next class with time remaining, upcoming reminders, and — only for
permitted users — BullDrop and Internlik summaries. Unpermitted modules are
absent from the response entirely.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bulldrop.models import BullDropAccount
from apps.images.models import Image
from apps.internlik.models import InternlikEntry
from apps.reminders.models import Reminder
from apps.schedule.models import ClassSchedule
from apps.schedule.services import next_class_for_user
from apps.vault.models import VaultItem


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
            entries = InternlikEntry.objects.filter(user=user)
            week_ahead = now + timedelta(days=7)
            payload["internlik"] = {
                "has_access": True,
                "active": entries.count(),
                "applications": entries.filter(kind=InternlikEntry.Kind.APPLICATION).count(),
                "interviews": entries.filter(kind=InternlikEntry.Kind.INTERVIEW).count(),
                "deadlines_soon": entries.filter(
                    deadline__isnull=False, deadline__gte=now, deadline__lte=week_ahead
                ).count(),
            }

        return Response(payload)


class GlobalSearchView(APIView):
    """Permission-aware global search across the user's own records.

    Only titles/names are searched and returned — never decrypted vault
    contents. Module results appear exclusively for users holding the
    corresponding permission; ownership is always scoped to request.user.
    """

    permission_classes = [permissions.IsAuthenticated]
    LIMIT_PER_GROUP = 5

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"query": query, "groups": []})

        user = request.user
        limit = self.LIMIT_PER_GROUP
        groups: list[dict] = []

        classes = ClassSchedule.objects.filter(user=user, group_name__icontains=query).order_by("group_name")[
            :limit
        ]
        if classes:
            groups.append(
                {
                    "type": "class",
                    "label": "classes.title",
                    "items": [
                        {"id": c.id, "title": c.group_name, "subtitle": c.start_time.strftime("%H:%M"), "url": "/classes"}
                        for c in classes
                    ],
                }
            )

        reminders = Reminder.objects.filter(user=user, title__icontains=query).order_by("remind_at")[:limit]
        if reminders:
            groups.append(
                {
                    "type": "reminder",
                    "label": "reminders.title",
                    "items": [
                        {"id": r.id, "title": r.title, "subtitle": "", "url": "/reminders"} for r in reminders
                    ],
                }
            )

        # Vault: titles only. Encrypted fields are never searched here — use
        # the in-vault search (which requires an explicit unlock flow) for that.
        vault_items = VaultItem.objects.filter(user=user, title__icontains=query).order_by("title")[:limit]
        if vault_items:
            groups.append(
                {
                    "type": "vault",
                    "label": "vault.title",
                    "items": [
                        {"id": v.id, "title": v.title, "subtitle": v.category, "url": "/vault"} for v in vault_items
                    ],
                }
            )

        # Images: names only, owner-scoped. Bytes stay password-protected.
        images = Image.objects.filter(owner=user, name__icontains=query).order_by("name")[:limit]
        if images:
            groups.append(
                {
                    "type": "image",
                    "label": "nav.images",
                    "items": [
                        {"id": i.id, "title": i.name, "subtitle": "", "url": "/images"} for i in images
                    ],
                }
            )

        if user.is_superuser or user.has_bulldrop_access:
            accounts = BullDropAccount.objects.filter(user=user, name__icontains=query).order_by("name")[:limit]
            if accounts:
                groups.append(
                    {
                        "type": "bulldrop",
                        "label": "nav.bulldrop",
                        "items": [
                            {"id": a.id, "title": a.name, "subtitle": a.get_browser_display(), "url": "/bulldrop"}
                            for a in accounts
                        ],
                    }
                )

        if user.is_superuser or user.has_internlik_access:
            entries = InternlikEntry.objects.filter(user=user, title__icontains=query).order_by("-updated_at")[
                :limit
            ]
            if entries:
                groups.append(
                    {
                        "type": "internlik",
                        "label": "nav.internlik",
                        "items": [
                            {"id": e.id, "title": e.title, "subtitle": e.kind, "url": "/internlik"} for e in entries
                        ],
                    }
                )

        return Response({"query": query, "groups": groups})