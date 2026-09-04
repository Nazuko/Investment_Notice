from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    settings_path = path or (CONFIG_DIR / "settings.yaml")
    with settings_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data


def holdings_yaml_path() -> Path:
    return CONFIG_DIR / "holdings.yaml"


def database_path(settings: dict[str, Any] | None = None) -> Path:
    settings = settings or load_settings()
    rel = settings.get("database_path", "data/bot.db")
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
