"""BullDrop account and claim models.

The claim timestamp is authoritative and stored server-side. The cooldown is
applied on read so a client can never manipulate the timer: the next
available time is always ``last_claim + cooldown`` computed in the backend.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.db import models
from django.utils import timezone


class BullDropAccount(models.Model):
    """Which browser the user runs this account in is chosen manually —
    the app never fingerprints or detects the user's real browser."""

    class Browser(models.TextChoices):
        CHROME = "chrome", "Google Chrome"
        OPERA = "opera", "Opera"
        DUCKDUCKGO = "duckduckgo", "DuckDuckGo"
        EDGE = "edge", "Microsoft Edge"
        FIREFOX = "firefox", "Firefox"
        BRAVE = "brave", "Brave"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bulldrop_accounts")
    name = models.CharField(max_length=120)
    username = models.CharField(max_length=120, blank=True, default="")
    browser = models.CharField(max_length=20, choices=Browser.choices, default=Browser.CHROME)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["user"])]

    def __str__(self):
        return f"{self.name} ({self.user_id})"

    @property
    def last_claim(self) -> "BullDropClaim | None":
        return self.claims.order_by("-claimed_at").first()

    @property
    def next_available_at(self) -> dt.datetime | None:
        last = self.last_claim
        if last is None:
            return None
        cooldown = dt.timedelta(seconds=settings.BULLDROP_COOLDOWN_SECONDS)
        return last.claimed_at + cooldown

    @property
    def status(self) -> str:
        """'ready' when claimable, else 'waiting'."""
        if self.next_available_at is None:
            return "ready"
        return "waiting" if self.next_available_at > timezone.now() else "ready"

    @property
    def remaining_seconds(self) -> int:
        next_at = self.next_available_at
        if next_at is None or next_at <= timezone.now():
            return 0
        return int((next_at - timezone.now()).total_seconds())


class BullDropClaim(models.Model):
    account = models.ForeignKey(BullDropAccount, on_delete=models.CASCADE, related_name="claims")
    claimed_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-claimed_at"]
        indexes = [models.Index(fields=["account", "-claimed_at"])]

    def __str__(self):
        return f"Claim {self.claimed_at:%Y-%m-%d %H:%M} {self.account_id}"