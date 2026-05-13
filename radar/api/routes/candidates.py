"""Read pre-rendered candidate Markdown and JSON exports for a given date."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from radar.utils import parse_date_arg

router = APIRouter(prefix="/candidates", tags=["candidates"])

REPORTS_DIR = Path("reports/candidates")
EXPORTS_DIR = Path("data/exports/candidates")


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return None


def _parse_date(value: str):
    try:
        return parse_date_arg(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid date: {exc}") from exc


@router.get("/markdown")
def get_candidate_markdown(date: Annotated[str, Query()] = "today") -> dict:
    target_date = _parse_date(date)
    path = REPORTS_DIR / f"{target_date.isoformat()}.md"
    if not path.exists():
        return {
            "date": target_date.isoformat(),
            "markdown": "",
            "mtime": None,
            "exists": False,
        }
    return {
        "date": target_date.isoformat(),
        "markdown": path.read_text(encoding="utf-8"),
        "mtime": _mtime_iso(path),
        "exists": True,
    }


@router.get("/export")
def get_candidate_export(date: Annotated[str, Query()] = "today") -> dict:
    target_date = _parse_date(date)
    path = EXPORTS_DIR / f"{target_date.isoformat()}.json"
    if not path.exists():
        return {
            "date": target_date.isoformat(),
            "candidates": [],
            "mtime": None,
            "exists": False,
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "date": target_date.isoformat(),
        "candidates": payload.get("candidates", []),
        "generated_at": payload.get("generated_at"),
        "mtime": _mtime_iso(path),
        "exists": True,
    }
