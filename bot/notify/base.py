from __future__ import annotations

from typing import Protocol

from bot.models import Signal


class Channel(Protocol):
    name: str

    def send(self, signal: Signal) -> None: ...


class Notifier:
    def __init__(self, channels: list[Channel]) -> None:
        self.channels = channels

    def notify(self, signal: Signal) -> None:
        for channel in self.channels:
            channel.send(signal)
