"""Stubs for additional notify channels. Wire them in settings when credentials exist."""

from __future__ import annotations

from bot.models import Signal


class TelegramChannel:
    name = "telegram"

    def send(self, signal: Signal) -> None:
        raise NotImplementedError("Telegram channel is not implemented yet")


class LineChannel:
    name = "line"

    def send(self, signal: Signal) -> None:
        raise NotImplementedError("LINE channel is not implemented yet")


class DiscordChannel:
    name = "discord"

    def send(self, signal: Signal) -> None:
        raise NotImplementedError("Discord channel is not implemented yet")
