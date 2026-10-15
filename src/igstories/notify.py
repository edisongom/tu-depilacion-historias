"""Notificaciones opcionales (Telegram). Si no hay credenciales, no hace nada."""

from __future__ import annotations

import logging
import os
from typing import Protocol

import requests

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, text: str, *, level: str = "info") -> None: ...


class NullNotifier:
    def notify(self, text: str, *, level: str = "info") -> None:
        log.debug("notify[%s]: %s", level, text)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, *, only_errors: bool = True):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._only_errors = only_errors

    def notify(self, text: str, *, level: str = "info") -> None:
        if self._only_errors and level == "info":
            return
        prefix = {"error": "❌", "warning": "⚠️"}.get(level, "✅")
        try:
            requests.post(
                self._url, data={"chat_id": self._chat_id, "text": f"{prefix} {text}"}, timeout=15
            )
        except requests.RequestException as exc:  # una notificación nunca debe romper el flujo
            log.warning("No se pudo enviar la notificación: %s", type(exc).__name__)


def from_env() -> Notifier:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        only_errors = os.environ.get("NOTIFY_SUCCESS", "").lower() not in ("1", "true", "yes")
        return TelegramNotifier(token, chat, only_errors=only_errors)
    return NullNotifier()
