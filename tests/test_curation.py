from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from radar.curation import (
    ProposalParseError,
    apply_proposals,
    parse_candidate_proposals,
    parse_proposals_file,
)
from radar.db import session_scope
from radar.models import Item, RadarDecision
from radar.schemas import RadarRing

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "candidates_filled.md"


def _add_item(session, *, item_id: int, title: str) -> None:
    item = Item(
        id=item_id,
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary="",
        url=f"https://example.test/{item_id}",
        pdf_url=None,
        published_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id=f"ext-{item_id}",
        arxiv_id=f"ext-{item_id}",
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )
    session.add(item)


def _seed_fixture_items(db_engine) -> None:
    with session_scope(db_engine) as session:
        _add_item(session, item_id=101, title="Robust BA Multi-Cam")
        _add_item(session, item_id=202, title="Niche Tracker")
        _add_item(session, item_id=303, title="Diffusion Detector")
        _add_item(session, item_id=404, title="Edge Deploy Paper")


def test_parse_fixture_yields_three_proposals_and_one_todo():
    proposals = parse_proposals_file(FIXTURE_PATH)
    assert len(proposals) == 4
    proposals_by_id = {p.item_id: p for p in proposals}
    assert proposals_by_id[101].proposal is not None
    assert proposals_by_id[101].proposal.ring == RadarRing.PROTOTYPE
    assert proposals_by_id[101].proposal.tracks == ["Calibration", "3D Geometry"]
    assert proposals_by_id[101].proposal.uncertain is False

    assert proposals_by_id[202].proposal is not None
    assert proposals_by_id[202].proposal.uncertain is True

    assert proposals_by_id[303].proposal is not None
    assert proposals_by_id[303].proposal.ring == RadarRing.IGNORE
    # tracks omitted -> None so record_decision falls back to classifier tracks
    assert proposals_by_id[303].proposal.tracks is None

    assert proposals_by_id[404].proposal is None
    assert proposals_by_id[404].skipped_reason == "still TODO"


def test_apply_happy_path_records_three_decisions(db_engine):
    _seed_fixture_items(db_engine)
    proposals = parse_proposals_file(FIXTURE_PATH)
    with session_scope(db_engine) as session:
        report = apply_proposals(session, proposals, decided_by="tester", dry_run=False)
    assert len(report.applied) == 3
    assert len(report.skipped) == 1
    with session_scope(db_engine) as session:
        rows = session.scalars(select(RadarDecision)).all()
        by_item = {row.item_id: (row.ring, row.uncertain) for row in rows}
    assert len(by_item) == 3
    assert by_item[101] == ("Prototype", False)
    assert by_item[202] == ("Watch", True)
    assert by_item[303] == ("Ignore", False)


def test_apply_dry_run_writes_nothing(db_engine):
    _seed_fixture_items(db_engine)
    proposals = parse_proposals_file(FIXTURE_PATH)
    with session_scope(db_engine) as session:
        report = apply_proposals(session, proposals, decided_by="tester", dry_run=True)
    assert len(report.applied) == 3
    with session_scope(db_engine) as session:
        count = len(session.scalars(select(RadarDecision)).all())
    assert count == 0


def test_apply_appends_and_warns_on_prior_decision(db_engine):
    _seed_fixture_items(db_engine)
    proposals = parse_proposals_file(FIXTURE_PATH)
    with session_scope(db_engine) as session:
        session.add(
            RadarDecision(
                item_id=101,
                ring=RadarRing.WATCH.value,
                tracks_json=["Calibration"],
                decision_reason="prior",
                action="",
                decided_by="prev",
                uncertain=False,
            )
        )
    with session_scope(db_engine) as session:
        report = apply_proposals(session, proposals, decided_by="tester", dry_run=False)
    with session_scope(db_engine) as session:
        count = len(
            session.scalars(select(RadarDecision).where(RadarDecision.item_id == 101)).all()
        )
    assert count == 2
    assert any("item 101" in warning for warning in report.warnings)


def test_parse_rejects_unknown_ring():
    text = _candidate_text(item_id=101, body="```yaml\nring: Maybe\nreason: bad\n```")
    with pytest.raises(ProposalParseError) as exc_info:
        parse_candidate_proposals(text)
    assert "ring" in str(exc_info.value)


def test_parse_rejects_malformed_yaml():
    text = _candidate_text(item_id=101, body="```yaml\nring: : :\nreason: x\n```")
    with pytest.raises(ProposalParseError) as exc_info:
        parse_candidate_proposals(text)
    assert exc_info.value.line_no > 0


def test_parse_rejects_missing_item_id():
    text = (
        "## Candidate 1: Some Title\n"
        "\n"
        "- Type: paper\n"
        "\n"
        "### Claude decision\n"
        "\n"
        "```yaml\nring: Watch\nreason: x\n```\n"
    )
    with pytest.raises(ProposalParseError) as exc_info:
        parse_candidate_proposals(text)
    assert "Item ID" in str(exc_info.value)


def test_parse_rejects_unterminated_fence():
    text = _candidate_text(item_id=101, body="```yaml\nring: Watch\nreason: x\n")
    with pytest.raises(ProposalParseError) as exc_info:
        parse_candidate_proposals(text)
    assert "unterminated" in str(exc_info.value).lower()


def test_parse_rejects_unexpected_fence_language():
    text = _candidate_text(item_id=101, body="```python\nring: Watch\n```")
    with pytest.raises(ProposalParseError) as exc_info:
        parse_candidate_proposals(text)
    assert "fence language" in str(exc_info.value)


def test_parse_accepts_yml_alias():
    text = _candidate_text(item_id=101, body="```yml\nring: Watch\nreason: x\n```")
    proposals = parse_candidate_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].proposal is not None
    assert proposals[0].proposal.ring == RadarRing.WATCH


def test_apply_raises_for_missing_item(db_engine):
    # Item 101 is not seeded -> record_decision raises DecisionError -> ProposalParseError
    text = _candidate_text(item_id=999, body="```yaml\nring: Watch\nreason: x\n```")
    proposals = parse_candidate_proposals(text)
    with (
        session_scope(db_engine) as session,
        pytest.raises(ProposalParseError),
    ):
        apply_proposals(session, proposals, decided_by="tester", dry_run=False)
    with session_scope(db_engine) as session:
        count = len(session.scalars(select(RadarDecision)).all())
    assert count == 0


def _candidate_text(*, item_id: int, body: str) -> str:
    return (
        "## Candidate 1: Test Item\n"
        "\n"
        f"- Item ID: {item_id}\n"
        "- Type: paper\n"
        "\n"
        "### Claude decision\n"
        "\n"
        f"{body}\n"
    )
