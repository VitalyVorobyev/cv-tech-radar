from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from radar.db import session_scope
from radar.filters.keyword_filter import upsert_classification
from radar.models import Item, ItemLLMJudgment
from radar.relevance_check import (
    DECISION_NO,
    DECISION_UNKNOWN,
    DECISION_YES,
    build_user_prompt,
    check_relevance_for_date,
    parse_judgment,
)
from radar.schemas import ChatSettings, ClassificationResult, RadarRing


class FakeClient:
    def __init__(self, replies: dict[str, str], *, raise_for: set[str] | None = None) -> None:
        self.replies = replies
        self.raise_for = raise_for or set()
        self.calls: list[str] = []

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append(prompt)
        if any(key in prompt for key in self.raise_for):
            msg = "simulated client failure"
            raise RuntimeError(msg)
        for key, reply in self.replies.items():
            if key in prompt:
                return reply
        return "DECISION: unknown\nREASON: no match"


def _settings(model: str = "gemma4:e2b") -> ChatSettings:
    return ChatSettings(
        enabled=True,
        model=model,
        base_url="http://ollama.test",
        timeout_seconds=5,
        temperature=0.0,
        max_tokens=64,
    )


def _make_classified_item(
    session,
    *,
    external_id: str,
    title: str,
    abstract: str,
    final: float,
    relevance: float = 50.0,
    published: datetime,
) -> Item:
    item = Item(
        type="paper",
        title=title,
        normalized_title=title.casefold(),
        abstract_or_summary=abstract,
        url=f"https://example.test/{external_id}",
        pdf_url=None,
        published_at=published,
        updated_at=None,
        source_name="arXiv cs.CV",
        external_id=external_id,
        arxiv_id=external_id,
        authors_json=[],
        organizations_json=[],
        metadata_json={},
    )
    session.add(item)
    session.flush()
    upsert_classification(
        session,
        item,
        ClassificationResult(
            tracks=[],
            positive_keywords=[],
            negative_keywords=[],
            relevance_score=relevance,
            novelty_score=0,
            source_priority_score=0,
            implementation_score=0,
            attention_score=0,
            final_score=final,
            negative_topic_penalty=0,
            recommended_ring=RadarRing.WATCH,
            confidence=0.5,
            rationale="seed",
        ),
    )
    return item


def test_build_user_prompt_includes_title_and_abstract(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        item = _make_classified_item(
            session,
            external_id="x",
            title="Camera Calibration",
            abstract="A study.",
            final=30,
            published=pub,
        )
        prompt = build_user_prompt(item)
    assert "Title: Camera Calibration" in prompt
    assert "Abstract:\nA study." in prompt


def test_build_user_prompt_handles_missing_abstract(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        item = _make_classified_item(
            session,
            external_id="y",
            title="Only Title",
            abstract="",
            final=30,
            published=pub,
        )
        prompt = build_user_prompt(item)
    assert prompt == "Title: Only Title\n"


def test_parse_judgment_yes():
    j = parse_judgment("DECISION: yes\nREASON: directly relevant for calibration.")
    assert j.decision == DECISION_YES
    assert j.reason == "directly relevant for calibration."


def test_parse_judgment_no_case_insensitive():
    j = parse_judgment("decision: No\nreason: outside scope.")
    assert j.decision == DECISION_NO
    assert j.reason == "outside scope."


def test_parse_judgment_tolerates_surrounding_text():
    raw = (
        "Sure, here is my analysis.\n"
        "DECISION: yes\n"
        "REASON: clear industrial CV fit.\n"
        "Hope this helps!"
    )
    j = parse_judgment(raw)
    assert j.decision == DECISION_YES
    assert j.reason == "clear industrial CV fit."


def test_parse_judgment_unknown_when_no_decision_line():
    j = parse_judgment("I don't know.")
    assert j.decision == DECISION_UNKNOWN
    assert j.reason == ""
    assert j.raw_response == "I don't know."


def test_check_relevance_writes_judgments_and_is_idempotent(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        _make_classified_item(
            session,
            external_id="good",
            title="Camera Calibration with Charuco",
            abstract="industrial calibration",
            final=80,
            published=pub,
        )
        _make_classified_item(
            session,
            external_id="bad",
            title="Animal 3D in the Wild",
            abstract="wildlife reconstruction",
            final=40,
            published=pub,
        )
        client = FakeClient(
            {
                "Camera Calibration with Charuco": (
                    "DECISION: yes\nREASON: industrial calibration topic."
                ),
                "Animal 3D in the Wild": "DECISION: no\nREASON: out of scope.",
            }
        )
        first = check_relevance_for_date(session, _settings(), date(2026, 5, 10), client=client)
        assert first.total == 2
        assert first.judged == 2
        assert first.skipped == 0
        assert first.yes_count == 1
        assert first.no_count == 1
        assert first.unknown_count == 0
        assert len(client.calls) == 2

        # Re-run: existing rows skip the client entirely.
        client2 = FakeClient({})
        second = check_relevance_for_date(session, _settings(), date(2026, 5, 10), client=client2)
        assert second.judged == 0
        assert second.skipped == 2
        assert client2.calls == []

        rows = session.scalars(select(ItemLLMJudgment)).all()
        assert {row.decision for row in rows} == {DECISION_YES, DECISION_NO}


def test_check_relevance_handles_client_failure_and_unknown(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        _make_classified_item(
            session,
            external_id="a",
            title="Calibration Paper",
            abstract="ok",
            final=80,
            published=pub,
        )
        _make_classified_item(
            session,
            external_id="b",
            title="Broken One",
            abstract="ok",
            final=70,
            published=pub,
        )
        _make_classified_item(
            session,
            external_id="c",
            title="Mystery Format",
            abstract="ok",
            final=60,
            published=pub,
        )
        client = FakeClient(
            replies={
                "Calibration Paper": "DECISION: yes\nREASON: fits.",
                "Mystery Format": "I think it's maybe relevant.",
            },
            raise_for={"Broken One"},
        )
        summary = check_relevance_for_date(session, _settings(), date(2026, 5, 10), client=client)

    assert summary.total == 3
    assert summary.judged == 2  # one OK, one unknown
    assert summary.failed == 1
    assert summary.yes_count == 1
    assert summary.no_count == 0
    assert summary.unknown_count == 1


def test_check_relevance_separates_by_model(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        _make_classified_item(
            session,
            external_id="a",
            title="X",
            abstract="ok",
            final=80,
            published=pub,
        )
        client_v1 = FakeClient({"X": "DECISION: yes\nREASON: m1"})
        client_v2 = FakeClient({"X": "DECISION: no\nREASON: m2"})
        first = check_relevance_for_date(
            session, _settings(model="m1"), date(2026, 5, 10), client=client_v1
        )
        assert first.judged == 1
        second = check_relevance_for_date(
            session, _settings(model="m2"), date(2026, 5, 10), client=client_v2
        )
        assert second.judged == 1  # different model — not skipped

        rows = session.scalars(select(ItemLLMJudgment)).all()
        by_model = {row.model: row.decision for row in rows}
        assert by_model == {"m1": DECISION_YES, "m2": DECISION_NO}


def test_check_relevance_skips_unclassified_and_zero_relevance_items(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        # Unclassified item (no row in item_classifications).
        unclassified = Item(
            type="paper",
            title="Unclassified",
            normalized_title="unclassified",
            abstract_or_summary="x",
            url="https://example.test/u",
            pdf_url=None,
            published_at=pub,
            updated_at=None,
            source_name="arXiv cs.CV",
            external_id="u",
            arxiv_id="u",
            authors_json=[],
            organizations_json=[],
            metadata_json={},
        )
        session.add(unclassified)
        # Classified item with relevance_score == 0 (still ignored).
        _make_classified_item(
            session,
            external_id="zero",
            title="Zero",
            abstract="x",
            final=0,
            relevance=0,
            published=pub,
        )
        # Classified positive item — must be judged.
        _make_classified_item(
            session,
            external_id="kept",
            title="Kept",
            abstract="x",
            final=30,
            published=pub,
        )
        client = FakeClient({"Kept": "DECISION: yes\nREASON: ok."})
        summary = check_relevance_for_date(session, _settings(), date(2026, 5, 10), client=client)

    assert summary.total == 1
    assert summary.judged == 1
    assert summary.yes_count == 1


def test_check_relevance_respects_limit(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        for index in range(5):
            _make_classified_item(
                session,
                external_id=f"x{index}",
                title=f"Item {index}",
                abstract="ok",
                final=90 - index,  # final descending so order is stable
                published=pub,
            )
        client = FakeClient({})  # all unknowns; not the point of this test
        summary = check_relevance_for_date(
            session, _settings(), date(2026, 5, 10), client=client, limit=3
        )

    assert summary.total == 3
    assert summary.judged == 3
    # Highest-scoring items should be the ones judged.
    assert {call.split("Title:")[1].split("\n")[0].strip() for call in client.calls} == {
        "Item 0",
        "Item 1",
        "Item 2",
    }


@pytest.mark.parametrize(
    "raw",
    [
        "DECISION:yes\nREASON: extra spaces missing",
        "  DECISION :  yes  \n  REASON :   trimmed ok ",
    ],
)
def test_parse_judgment_tolerates_whitespace_variants(raw: str):
    j = parse_judgment(raw)
    assert j.decision == DECISION_YES


def test_check_relevance_rejudge_replaces_existing_rows(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    with session_scope(db_engine) as session:
        item = _make_classified_item(
            session,
            external_id="x",
            title="Camera Calibration",
            abstract="ok",
            final=80,
            published=pub,
        )
        # Pre-existing empty unknown — what the user has after the bad first run.
        session.add(
            ItemLLMJudgment(
                item_id=item.id,
                model="gemma4:e2b",
                decision=DECISION_UNKNOWN,
                reason="",
                raw_response="",
            )
        )
        session.flush()

        # Without --rejudge: skipped, existing row untouched.
        client_skip = FakeClient({})
        skip_summary = check_relevance_for_date(
            session, _settings(), date(2026, 5, 10), client=client_skip
        )
        assert skip_summary.skipped == 1
        assert skip_summary.judged == 0
        assert client_skip.calls == []
        existing = session.scalars(select(ItemLLMJudgment)).all()
        assert len(existing) == 1
        assert existing[0].decision == DECISION_UNKNOWN

        # With --rejudge: existing row replaced with the new judgment.
        client_redo = FakeClient({"Camera Calibration": "DECISION: yes\nREASON: industrial fit."})
        redo_summary = check_relevance_for_date(
            session,
            _settings(),
            date(2026, 5, 10),
            client=client_redo,
            rejudge=True,
        )
        assert redo_summary.judged == 1
        assert redo_summary.skipped == 0
        assert redo_summary.yes_count == 1
        rows = session.scalars(select(ItemLLMJudgment)).all()
        assert len(rows) == 1
        assert rows[0].decision == DECISION_YES
        assert rows[0].reason == "industrial fit."


def test_check_relevance_invokes_on_progress_for_every_outcome(db_engine):
    pub = datetime(2026, 5, 10, 10, 0, tzinfo=UTC)
    events: list[tuple[int, int, str, str]] = []

    def cb(index: int, total: int, item, outcome: str) -> None:
        events.append((index, total, item.external_id, outcome))

    with session_scope(db_engine) as session:
        _make_classified_item(
            session,
            external_id="judged-yes",
            title="Calibration",
            abstract="ok",
            final=90,
            published=pub,
        )
        _make_classified_item(
            session,
            external_id="judged-no",
            title="Out of scope",
            abstract="ok",
            final=80,
            published=pub,
        )
        _make_classified_item(
            session,
            external_id="will-fail",
            title="Broken One",
            abstract="ok",
            final=70,
            published=pub,
        )
        # Pre-seed a judgment so the next item is skipped.
        from radar.models import ItemLLMJudgment

        already = _make_classified_item(
            session,
            external_id="already",
            title="Pre-existing",
            abstract="ok",
            final=60,
            published=pub,
        )
        session.add(
            ItemLLMJudgment(
                item_id=already.id,
                model="gemma4:e2b",
                decision=DECISION_YES,
                reason="prior",
                raw_response="prior",
            )
        )
        session.flush()

        client = FakeClient(
            replies={
                "Calibration": "DECISION: yes\nREASON: ok.",
                "Out of scope": "DECISION: no\nREASON: nope.",
            },
            raise_for={"Broken One"},
        )
        check_relevance_for_date(
            session,
            _settings(),
            date(2026, 5, 10),
            client=client,
            on_progress=cb,
        )

    # 4 items × one callback each, in score-descending order.
    assert [e[3] for e in events] == ["yes", "no", "failed", "skipped"]
    assert [e[0] for e in events] == [1, 2, 3, 4]
    assert {e[1] for e in events} == {4}
    assert [e[2] for e in events] == ["judged-yes", "judged-no", "will-fail", "already"]
