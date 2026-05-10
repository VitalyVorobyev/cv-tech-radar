from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_title(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title).strip().casefold()
    normalized = re.sub(r"[^\w\s.-]", "", normalized)
    return normalized


def normalize_whitespace(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_date_arg(value: str) -> date:
    if value == "today":
        return datetime.now().date()
    return date.fromisoformat(value)


def date_bounds(target: date) -> tuple[datetime, datetime]:
    start = datetime(target.year, target.month, target.day, tzinfo=UTC)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
    return start, end
