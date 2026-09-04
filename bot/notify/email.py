from __future__ import annotations

import smtplib
from email.message import EmailMessage

from bot.config import env
from bot.models import Signal


class EmailChannel:
    name = "email"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        mail_from: str | None = None,
        to: list[str] | None = None,
    ) -> None:
        self.host = host or env("SMTP_HOST", "smtp.gmail.com")
        self.port = port if port is not None else int(env("SMTP_PORT", "587") or "587")
        self.user = user if user is not None else env("SMTP_USER")
        self.password = password if password is not None else env("SMTP_PASSWORD")
        self.mail_from = mail_from or env("SMTP_FROM") or self.user
        extra = env("ALERT_EMAIL_TO")
        self.to = list(to or [])
        if extra:
            self.to.extend(part.strip() for part in extra.split(",") if part.strip())

    def send(self, signal: Signal) -> None:
        if not self.to:
            raise RuntimeError("Email channel has no recipients (set ALERT_EMAIL_TO or settings.email.to)")
        if not self.user or not self.password:
            raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set to send email")

        msg = EmailMessage()
        msg["Subject"] = f"[{signal.side.upper()}] {signal.symbol} @ {signal.price}"
        msg["From"] = self.mail_from
        msg["To"] = ", ".join(self.to)
        msg.set_content(
            "\n".join(
                [
                    f"Action: {signal.side.upper()}",
                    f"Symbol: {signal.symbol}",
                    f"Price: {signal.price}",
                    f"Rule: {signal.rule_id}",
                    f"Reason: {signal.reason}",
                    f"Meta: {signal.meta}",
                ]
            )
        )

        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.send_message(msg)
