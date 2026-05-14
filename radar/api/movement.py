from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

Movement = Literal["new", "in", "out"]

# Inner ring = lower index = closer to centre.
RING_RADIUS_ORDER: dict[str, int] = {
    "Use": 0,
    "Prototype": 1,
    "Evaluate": 2,
    "Watch": 3,
    "Ignore": 4,
}

DEFAULT_WINDOW_DAYS = 7


def _ensure_utc(moment: datetime) -> datetime:
    """SQLite drops tzinfo on read even though the column is DateTime(timezone=True)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def classify_movement(
    *,
    current_ring: str,
    previous_ring: str | None,
    decided_at: datetime,
    first_decided_at: datetime | None,
    now: datetime,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Movement | None:
    """Classify how this item moved in the last ``window_days``.

    Rules (per design handoff §API additions):
      - "new":  first decision is within ``window_days`` AND lands in Use/Prototype/Evaluate.
      - "in":   last decision is within ``window_days`` AND moves toward the centre
                (e.g. Watch -> Evaluate, Evaluate -> Prototype, Prototype -> Use).
      - "out":  last decision is within ``window_days`` AND moves away from the centre.
      - None:   no qualifying movement in the window.

    The "new" classification takes precedence over "in".
    """
    threshold = _ensure_utc(now) - timedelta(days=window_days)
    decided_at = _ensure_utc(decided_at)
    if first_decided_at is not None:
        first_decided_at = _ensure_utc(first_decided_at)

    if (
        first_decided_at is not None
        and first_decided_at >= threshold
        and current_ring in {"Use", "Prototype", "Evaluate"}
    ):
        return "new"

    if previous_ring is not None and decided_at >= threshold:
        prev_idx = RING_RADIUS_ORDER.get(previous_ring)
        curr_idx = RING_RADIUS_ORDER.get(current_ring)
        if prev_idx is None or curr_idx is None or prev_idx == curr_idx:
            return None
        if curr_idx < prev_idx:
            return "in"
        return "out"

    return None
