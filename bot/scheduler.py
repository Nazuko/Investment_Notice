from __future__ import annotations

from typing import Any, Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger


def serve(settings: dict[str, Any], job: Callable[[], None]) -> None:
    minutes = int(settings.get("poll_interval_minutes") or 15)
    timezone = settings.get("timezone") or "UTC"
    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(job, IntervalTrigger(minutes=minutes), id="tick")
    print(f"Serving ticks every {minutes} minute(s) ({timezone}). Ctrl+C to stop.")
    job()
    scheduler.start()
