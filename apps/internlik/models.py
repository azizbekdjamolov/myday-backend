"""Internlik records.

A deliberately minimal, extensible model: every entry is owned by exactly one
user and hidden from everyone else. Fields are kept generic so the module can
evolve (company, role, application status, deadlines, notes, ...) without
schema churn — additional structured fields can be added later without
touching the access-control surface.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class InternlikEntry(models.Model):
    class Kind(models.TextChoices):
        NOTE = "note", "Note"
        APPLICATION = "application", "Application"
        INTERVIEW = "interview", "Interview"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="internlik_entries")
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.NOTE)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "kind"])]

    def __str__(self):
        return f"{self.title} ({self.user_id})"