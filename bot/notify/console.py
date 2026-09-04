from __future__ import annotations

from bot.models import Signal


class ConsoleChannel:
    name = "console"

    def send(self, signal: Signal) -> None:
        print(
            f"[{signal.side.upper()}] {signal.symbol} @ {signal.price} "
            f"({signal.rule_id}) {signal.reason}"
        )


class RecordingChannel:
    """Test double that records signals instead of sending them."""

    name = "recording"

    def __init__(self) -> None:
        self.sent: list[Signal] = []

    def send(self, signal: Signal) -> None:
        self.sent.append(signal)
