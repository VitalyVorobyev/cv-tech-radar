from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from radar.api.movement import classify_movement

NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # "new": first decision within 7d and lands in Use/Prototype/Evaluate
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring=None,
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=1),
            ),
            "new",
            id="new-into-Use",
        ),
        pytest.param(
            dict(
                current_ring="Prototype",
                previous_ring=None,
                decided_at=NOW - timedelta(days=2),
                first_decided_at=NOW - timedelta(days=2),
            ),
            "new",
            id="new-into-Prototype",
        ),
        pytest.param(
            dict(
                current_ring="Evaluate",
                previous_ring=None,
                decided_at=NOW - timedelta(days=3),
                first_decided_at=NOW - timedelta(days=3),
            ),
            "new",
            id="new-into-Evaluate",
        ),
        # "new" excluded when landing ring is Watch
        pytest.param(
            dict(
                current_ring="Watch",
                previous_ring=None,
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=1),
            ),
            None,
            id="watch-landing-is-not-new",
        ),
        # "new" excluded when first_decided_at is older than 7d
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring=None,
                decided_at=NOW - timedelta(days=20),
                first_decided_at=NOW - timedelta(days=20),
            ),
            None,
            id="old-first-decision-is-not-new",
        ),
        # "in" movements: toward center
        pytest.param(
            dict(
                current_ring="Evaluate",
                previous_ring="Watch",
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=30),
            ),
            "in",
            id="in-Watch-to-Evaluate",
        ),
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring="Prototype",
                decided_at=NOW - timedelta(days=2),
                first_decided_at=NOW - timedelta(days=30),
            ),
            "in",
            id="in-Prototype-to-Use",
        ),
        # "out": away from center
        pytest.param(
            dict(
                current_ring="Watch",
                previous_ring="Use",
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=30),
            ),
            "out",
            id="out-Use-to-Watch",
        ),
        pytest.param(
            dict(
                current_ring="Evaluate",
                previous_ring="Prototype",
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=30),
            ),
            "out",
            id="out-Prototype-to-Evaluate",
        ),
        # None: previous == current
        pytest.param(
            dict(
                current_ring="Watch",
                previous_ring="Watch",
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=30),
            ),
            None,
            id="same-ring-no-movement",
        ),
        # None: decided_at older than 7d
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring="Watch",
                decided_at=NOW - timedelta(days=20),
                first_decided_at=NOW - timedelta(days=30),
            ),
            None,
            id="old-decision-no-movement",
        ),
        # None: previous_ring is None and first_decided_at older than 7d
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring=None,
                decided_at=NOW - timedelta(days=20),
                first_decided_at=NOW - timedelta(days=20),
            ),
            None,
            id="old-first-decision-no-previous",
        ),
        # Edge: decided_at exactly at threshold (now - 7d) — included (>= threshold)
        pytest.param(
            dict(
                current_ring="Evaluate",
                previous_ring="Watch",
                decided_at=NOW - timedelta(days=7),
                first_decided_at=NOW - timedelta(days=30),
            ),
            "in",
            id="decided-at-threshold-included",
        ),
        # "new" precedence over "in": both qualify -> "new"
        pytest.param(
            dict(
                current_ring="Use",
                previous_ring="Watch",
                decided_at=NOW - timedelta(days=1),
                first_decided_at=NOW - timedelta(days=1),
            ),
            "new",
            id="new-precedes-in",
        ),
    ],
)
def test_classify_movement(kwargs: dict, expected: str | None) -> None:
    assert classify_movement(now=NOW, **kwargs) == expected
