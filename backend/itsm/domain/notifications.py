"""
Notifications: OBSERVER (NotificationService listens to events) + ADAPTER (SMS).

Adding Slack, Teams, Discord or push = one new NotificationChannel subclass.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .events import DomainEvent, EventObserver


@dataclass(frozen=True)
class Notification:
    recipient_id: str
    address: str
    channel: str
    subject: str
    body: str
    at: datetime
    urgent: bool


class NotificationChannel(ABC):
    """A delivery mechanism."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def send(self, notification: Notification) -> None: ...

    def address_for(self, user) -> str:
        return user.user_id


class InAppChannel(NotificationChannel):
    """Dashboard bell icon: an inbox per user, which the frontend reads."""
    name = "in_app"

    def __init__(self):
        self._inboxes: dict[str, list[Notification]] = defaultdict(list)

    def send(self, notification: Notification) -> None:
        self._inboxes[notification.recipient_id].append(notification)

    def inbox(self, user_id: str) -> list[Notification]:
        return list(self._inboxes.get(user_id, []))


class EmailChannel(NotificationChannel):
    """Simulated email (keeps an outbox). Can be swapped for real SMTP (smtplib)."""
    name = "email"

    def __init__(self):
        self._outbox: list[Notification] = []

    def address_for(self, user) -> str:
        return user.email

    def send(self, notification: Notification) -> None:
        self._outbox.append(notification)

    @property
    def outbox(self) -> list[Notification]:
        return list(self._outbox)


class ThirdPartySmsGateway:
    """Pretend vendor SDK with its own, incompatible API that we cannot change."""

    def __init__(self):
        self.sent: list[dict] = []

    def dispatch_text(self, msisdn: str, text: str, priority_flag: int) -> str:
        self.sent.append({"to": msisdn, "text": text, "flag": priority_flag})
        return f"MSG-{len(self.sent)}"


class SmsChannelAdapter(NotificationChannel):
    """ADAPTER PATTERN: makes the vendor SMS SDK look like one of our NotificationChannels."""
    name = "sms"
    SMS_LIMIT = 160

    def __init__(self, gateway: ThirdPartySmsGateway, phone_book: dict[str, str] | None = None):
        self._gateway = gateway
        self._phones = dict(phone_book or {})

    def address_for(self, user) -> str:
        return self._phones.get(user.user_id, "+910000000000")

    def send(self, n: Notification) -> None:
        self._gateway.dispatch_text(n.address, f"[I-ITSM] {n.subject}"[:self.SMS_LIMIT], 1 if n.urgent else 3)


class NotificationService(EventObserver):
    """
    Turns events into notifications with a channel-selection policy:
      urgent events (P1, SLA breach, escalation) → every channel (in-app + email + SMS…)
      normal events                              → in-app + email only
    A failing channel is logged and skipped; it never breaks the incident workflow.
    """
    NORMAL = {"in_app", "email"}

    def __init__(self, user_lookup: Callable[[str], object | None]):
        self._lookup = user_lookup
        self._channels: dict[str, NotificationChannel] = {}
        self._failures: list[str] = []

    def register_channel(self, channel: NotificationChannel) -> None:
        self._channels[channel.name] = channel

    def channel(self, name: str) -> NotificationChannel:
        return self._channels[name]

    @property
    def delivery_failures(self) -> list[str]:
        return list(self._failures)

    def _select(self, event: DomainEvent) -> list[NotificationChannel]:
        if event.urgent:
            return list(self._channels.values())
        return [c for n, c in self._channels.items() if n in self.NORMAL]

    def on_event(self, event: DomainEvent) -> None:
        subject = f"{event.incident_id}: {event.type.name.replace('_', ' ').capitalize()}"
        for rid in dict.fromkeys(event.recipients):           # de-duplicate, keep order
            user = self._lookup(rid)
            if user is None:
                continue
            for ch in self._select(event):
                try:
                    ch.send(Notification(rid, ch.address_for(user), ch.name, subject,
                                         event.description, event.at, event.urgent))
                except Exception as ex:                        # one broken channel never breaks the rest
                    self._failures.append(f"{ch.name} → {rid}: {ex}")
