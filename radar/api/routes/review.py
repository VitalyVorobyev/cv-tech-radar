"""The review inbox — the manual gate's working surface.

Agent-authored decisions (``radar apply``) are recorded as unconfirmed
proposals and stay off the radar. This module lists them and lets a human
ratify, override or dismiss them. Confirming is the *only* way a paper reaches
the board, the digest, or the public static bundle.

An item is "pending" when its most recent decision of any kind is still
unconfirmed. That definition needs no extra bookkeeping: confirming a proposal,
or superseding it with a human decision at a different ring, removes the item
from the inbox as a side effect.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from radar.api.deps import get_session
from radar.api.routes.queue import latest_llm_judgments
from radar.api.schemas import (
    ArtifactDecisionCreatedOut,
    CandidateScoresOut,
    ConfirmBulkResult,
    ConfirmedOut,
    DismissBulkResult,
    EcosystemReviewConfirmRequest,
    EcosystemReviewItemOut,
    EcosystemReviewResponse,
    ReviewBulkConfirmRequest,
    ReviewBulkDismissRequest,
    ReviewConfirmRequest,
    ReviewCountsOut,
    ReviewItemOut,
    ReviewProposalOut,
    ReviewResponse,
    ReviewSummaryResponse,
)
from radar.artifact_decisions import (
    confirm_artifact_decision,
    latest_pending_artifact_decision,
    record_artifact_decision,
)
from radar.decisions import (
    DecisionError,
    confirm_decision,
    latest_pending_decision_subq,
    record_decision,
)
from radar.models import Artifact, ArtifactDecision, Item, ItemClassification, RadarDecision
from radar.reports.ecosystem import seed_ring
from radar.schemas import DecisionOrigin, RadarRing

router = APIRouter(tags=["review"])

DEFAULT_DISMISS_REASON = "Dismissed in review."

# Most-attention-first, so the rings that matter surface at the top of the
# backlog. Ignore proposals sort last and are hidden unless asked for.
_RING_RANK = {
    RadarRing.USE.value: 0,
    RadarRing.PROTOTYPE.value: 1,
    RadarRing.EVALUATE.value: 2,
    RadarRing.WATCH.value: 3,
    RadarRing.IGNORE.value: 4,
}


@router.get("/review", response_model=ReviewResponse)
def get_review(
    session: Annotated[Session, Depends(get_session)],
    ring: Annotated[RadarRing | None, Query()] = None,
    track: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    include_ignore: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewResponse:
    pending_ids = latest_pending_decision_subq().subquery()
    decision = aliased(RadarDecision)
    base = (
        select(Item, decision, ItemClassification.final_score)
        .join(pending_ids, decision.id == pending_ids.c.id)
        .join(Item, Item.id == decision.item_id)
        .outerjoin(ItemClassification, ItemClassification.item_id == Item.id)
    )
    if not include_ignore:
        base = base.where(decision.ring != RadarRing.IGNORE.value)
    if ring is not None:
        base = base.where(decision.ring == ring.value)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(func.lower(Item.title).like(like))

    rows = list(session.execute(base).all())
    # Track filtering happens in Python: tracks live in a JSON column and the
    # pending set is small enough (hundreds, not millions) that a portable
    # in-memory filter beats a dialect-specific JSON query.
    if track is not None:
        rows = [row for row in rows if track in (row[1].tracks_json or [])]

    rows.sort(
        key=lambda row: (
            _RING_RANK.get(row[1].ring, len(_RING_RANK)),
            -(row[2] or 0.0),
            row[0].title.lower(),
        )
    )
    pending_total = len(rows)
    page = rows[offset : offset + limit]

    judgments = latest_llm_judgments(session, [item.id for item, _, _ in page])
    previous_rings = _previous_confirmed_rings(session, [item.id for item, _, _ in page])

    items = [
        ReviewItemOut(
            id=item.id,
            type=str(item.type),
            title=item.title,
            abstract=item.abstract_or_summary or "",
            url=item.url,
            pdf_url=item.pdf_url,
            source=item.source_name,
            published_at=item.published_at,
            tracks=proposal.tracks_json or [],
            scores=_scores_out(session, item.id, score),
            proposal=ReviewProposalOut(
                decision_id=proposal.id,
                ring=proposal.ring,
                tracks=proposal.tracks_json or [],
                reason=proposal.decision_reason or "",
                action=proposal.action or "",
                uncertain=bool(proposal.uncertain),
                decided_by=proposal.decided_by or "",
                created_at=proposal.created_at,
            ),
            previous_confirmed_ring=previous_rings.get(item.id),
            llm_judgment=judgments.get(item.id),
        )
        for item, proposal, score in page
    ]

    return ReviewResponse(
        pending_total=pending_total,
        counts=_pending_counts(session),
        items=items,
    )


@router.get("/review/summary", response_model=ReviewSummaryResponse)
def get_review_summary(
    session: Annotated[Session, Depends(get_session)],
) -> ReviewSummaryResponse:
    """Cheap backlog sizes for the nav badge."""
    return ReviewSummaryResponse(
        papers_pending=_pending_paper_count(session, include_ignore=False),
        ecosystem_pending=len(_pending_artifacts(session)),
    )


@router.post("/review/confirm", response_model=ConfirmedOut)
def post_review_confirm(
    payload: ReviewConfirmRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ConfirmedOut:
    try:
        decision = confirm_decision(
            session,
            decision_id=payload.decision_id,
            confirmed_by=payload.confirmed_by,
        )
    except DecisionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.flush()
    assert decision.confirmed_at is not None
    return ConfirmedOut(
        decision_id=decision.id,
        item_id=decision.item_id,
        ring=decision.ring,
        confirmed_at=decision.confirmed_at,
    )


@router.post("/review/confirm-bulk", response_model=ConfirmBulkResult)
def post_review_confirm_bulk(
    payload: ReviewBulkConfirmRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ConfirmBulkResult:
    """Ratify many proposals at once — the backlog would be unusable without it.

    Individual failures are reported rather than aborting the batch, so one
    stale id cannot cost the curator a whole screenful of work.
    """
    confirmed: list[int] = []
    failed: list[dict[str, object]] = []
    for decision_id in payload.decision_ids:
        try:
            confirm_decision(
                session,
                decision_id=decision_id,
                confirmed_by=payload.confirmed_by,
            )
        except DecisionError as exc:
            failed.append({"decision_id": decision_id, "error": str(exc)})
            continue
        confirmed.append(decision_id)
    session.flush()
    return ConfirmBulkResult(confirmed=confirmed, failed=failed)


@router.post("/review/dismiss-bulk", response_model=DismissBulkResult)
def post_review_dismiss_bulk(
    payload: ReviewBulkDismissRequest,
    session: Annotated[Session, Depends(get_session)],
) -> DismissBulkResult:
    """Record human ``Ignore`` decisions, clearing items out of the inbox.

    Dismissing is a real decision, not a hide: the row joins the negative
    corpus that scoring work is calibrated against, this time with a human
    label on it.
    """
    reason = payload.reason.strip() or DEFAULT_DISMISS_REASON
    dismissed: list[int] = []
    failed: list[dict[str, object]] = []
    for item_id in payload.item_ids:
        try:
            record_decision(
                session,
                item_id=item_id,
                ring=RadarRing.IGNORE,
                tracks=None,
                reason=reason,
                action="",
                decided_by=payload.decided_by,
                origin=DecisionOrigin.HUMAN,
            )
        except DecisionError as exc:
            failed.append({"item_id": item_id, "error": str(exc)})
            continue
        dismissed.append(item_id)
    session.flush()
    return DismissBulkResult(dismissed=dismissed, failed=failed)


@router.get("/ecosystem/review", response_model=EcosystemReviewResponse)
def get_ecosystem_review(
    session: Annotated[Session, Depends(get_session)],
) -> EcosystemReviewResponse:
    """Enabled artifacts that are not yet on the ecosystem radar.

    An artifact with no decision at all still shows up here: its
    :func:`seed_ring` is offered as a suggestion, but the artifact is only
    placed once a human confirms it.
    """
    rows = _pending_artifacts(session)
    items = [
        EcosystemReviewItemOut(
            artifact_id=artifact.id,
            key=artifact.key,
            name=artifact.name,
            description=artifact.description,
            status=artifact.status,
            capability=artifact.capability,
            homepage_url=artifact.homepage_url,
            ecosystems=sorted({ref.ecosystem for ref in artifact.refs}),
            tracks=artifact.tracks_json or [],
            suggested_ring=(proposal.ring if proposal is not None else seed_ring(artifact.status)),
            proposal=(
                ReviewProposalOut(
                    decision_id=proposal.id,
                    ring=proposal.ring,
                    tracks=proposal.tracks_json or [],
                    reason=proposal.decision_reason or "",
                    action=proposal.action or "",
                    uncertain=bool(proposal.uncertain),
                    decided_by=proposal.decided_by or "",
                    created_at=proposal.created_at,
                )
                if proposal is not None
                else None
            ),
        )
        for artifact, proposal in rows
    ]
    return EcosystemReviewResponse(pending_total=len(items), items=items)


@router.post(
    "/ecosystem/review/confirm",
    response_model=ArtifactDecisionCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def post_ecosystem_review_confirm(
    payload: EcosystemReviewConfirmRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ArtifactDecisionCreatedOut:
    """Put an artifact on the ecosystem radar.

    With a pending proposal and no ring override, the proposal is ratified in
    place so the audit trail keeps "proposed by X, confirmed by you". Otherwise
    a fresh human decision is recorded at the requested ring (defaulting to the
    artifact's seed ring).
    """
    artifact = session.get(Artifact, payload.artifact_id)
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"artifact {payload.artifact_id} not found",
        )

    pending = latest_pending_artifact_decision(session, artifact.id)
    if pending is not None and (payload.ring is None or payload.ring.value == pending.ring):
        decision = confirm_artifact_decision(
            session, decision_id=pending.id, confirmed_by=payload.decided_by
        )
        session.flush()
        assert decision.confirmed_at is not None
        return ArtifactDecisionCreatedOut(decision_id=decision.id, created_at=decision.confirmed_at)

    ring = payload.ring or RadarRing(seed_ring(artifact.status))
    reason = payload.reason.strip() or f"Confirmed onto the radar as {ring.value}."
    try:
        decision = record_artifact_decision(
            session,
            artifact_id=artifact.id,
            ring=ring,
            tracks=None,
            reason=reason,
            action="",
            decided_by=payload.decided_by,
            origin=DecisionOrigin.HUMAN,
        )
    except DecisionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.flush()
    return ArtifactDecisionCreatedOut(decision_id=decision.id, created_at=decision.created_at)


# --- helpers ----------------------------------------------------------------


def _scores_out(session: Session, item_id: int, final: float | None) -> CandidateScoresOut:
    classification = session.scalar(
        select(ItemClassification).where(ItemClassification.item_id == item_id)
    )
    if classification is None:
        return CandidateScoresOut(
            relevance=0.0,
            source_priority=0.0,
            implementation=0.0,
            attention=0.0,
            novelty=0.0,
            negative_penalty=0.0,
            final=final or 0.0,
        )
    return CandidateScoresOut(
        relevance=classification.relevance_score,
        source_priority=classification.source_priority_score,
        implementation=classification.implementation_score,
        attention=classification.attention_score,
        novelty=classification.novelty_score,
        negative_penalty=classification.negative_topic_penalty,
        final=classification.final_score,
    )


def _previous_confirmed_rings(session: Session, item_ids: list[int]) -> dict[int, str]:
    """Latest confirmed ring per item — context for "this used to be Watch"."""
    if not item_ids:
        return {}
    rows = session.execute(
        select(RadarDecision.item_id, RadarDecision.ring, RadarDecision.created_at)
        .where(
            RadarDecision.item_id.in_(item_ids),
            RadarDecision.confirmed_at.is_not(None),
        )
        .order_by(RadarDecision.created_at.desc(), RadarDecision.id.desc())
    ).all()
    out: dict[int, str] = {}
    for item_id, ring, _created in rows:
        out.setdefault(item_id, ring)
    return out


def _pending_paper_count(session: Session, *, include_ignore: bool) -> int:
    pending_ids = latest_pending_decision_subq().subquery()
    decision = aliased(RadarDecision)
    stmt = (
        select(func.count())
        .select_from(decision)
        .join(pending_ids, decision.id == pending_ids.c.id)
    )
    if not include_ignore:
        stmt = stmt.where(decision.ring != RadarRing.IGNORE.value)
    return int(session.scalar(stmt) or 0)


def _pending_counts(session: Session) -> ReviewCountsOut:
    """Pending counts per proposed ring, unfiltered — drives the filter chips."""
    pending_ids = latest_pending_decision_subq().subquery()
    decision = aliased(RadarDecision)
    rows = session.execute(
        select(decision.ring, func.count())
        .select_from(decision)
        .join(pending_ids, decision.id == pending_ids.c.id)
        .group_by(decision.ring)
    ).all()
    counts = dict(rows)
    return ReviewCountsOut(
        Use=counts.get(RadarRing.USE.value, 0),
        Prototype=counts.get(RadarRing.PROTOTYPE.value, 0),
        Evaluate=counts.get(RadarRing.EVALUATE.value, 0),
        Watch=counts.get(RadarRing.WATCH.value, 0),
        Ignore=counts.get(RadarRing.IGNORE.value, 0),
    )


def _pending_artifacts(session: Session) -> list[tuple[Artifact, ArtifactDecision | None]]:
    """Enabled artifacts with no confirmed decision, newest proposal attached."""
    artifacts = list(
        session.scalars(
            select(Artifact).where(Artifact.enabled.is_(True)).order_by(Artifact.name.asc())
        )
    )
    out: list[tuple[Artifact, ArtifactDecision | None]] = []
    for artifact in artifacts:
        confirmed = session.scalar(
            select(ArtifactDecision.id)
            .where(
                ArtifactDecision.artifact_id == artifact.id,
                ArtifactDecision.confirmed_at.is_not(None),
            )
            .limit(1)
        )
        if confirmed is not None:
            continue
        out.append((artifact, latest_pending_artifact_decision(session, artifact.id)))
    return out
