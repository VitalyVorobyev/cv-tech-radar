from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from radar.utils import utc_now


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    url: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")

    raw_items: Mapped[list[RawItem]] = relationship(back_populates="source")


class RawItem(Base):
    __tablename__ = "raw_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_raw_source_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(240), index=True)
    url: Mapped[str] = mapped_column(Text)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    source: Mapped[Source] = relationship(back_populates="raw_items")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_item_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    abstract_or_summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_name: Mapped[str] = mapped_column(String(240), index=True)
    external_id: Mapped[str | None] = mapped_column(String(240), index=True)
    doi: Mapped[str | None] = mapped_column(String(240))
    arxiv_id: Mapped[str | None] = mapped_column(String(120), index=True)
    authors_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    organizations_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    first_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    classification: Mapped[ItemClassification | None] = relationship(
        back_populates="item", uselist=False, cascade="all, delete-orphan"
    )
    decisions: Mapped[list[RadarDecision]] = relationship(back_populates="item")


class ItemClassification(Base):
    __tablename__ = "item_classifications"
    __table_args__ = (UniqueConstraint("item_id", name="uq_classification_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    tracks_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    positive_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    negative_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    novelty_score: Mapped[float] = mapped_column(Float, default=0)
    source_priority_score: Mapped[float] = mapped_column(Float, default=0)
    implementation_score: Mapped[float] = mapped_column(Float, default=0)
    attention_score: Mapped[float] = mapped_column(Float, default=0)
    negative_topic_penalty: Mapped[float] = mapped_column(Float, default=0)
    final_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    recommended_ring: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[Item] = relationship(back_populates="classification")


class RadarDecision(Base):
    __tablename__ = "radar_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    ring: Mapped[str] = mapped_column(String(40), index=True)
    tracks_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(120), default="")
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    previous_ring: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[Item] = relationship(back_populates="decisions")


class ItemEmbedding(Base):
    __tablename__ = "item_embeddings"
    __table_args__ = (UniqueConstraint("item_id", "model", name="uq_embedding_item_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    model: Mapped[str] = mapped_column(String(120), index=True)
    vector_json: Mapped[list[float]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[Item] = relationship()


class ItemLLMJudgment(Base):
    __tablename__ = "item_llm_judgments"
    __table_args__ = (UniqueConstraint("item_id", "model", name="uq_llm_item_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    model: Mapped[str] = mapped_column(String(120), index=True)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[Item] = relationship()


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("kind", "date", name="uq_digest_kind_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(Text)
    markdown_path: Mapped[str] = mapped_column(Text)
    json_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# --- Ecosystem monitoring ---------------------------------------------------
#
# Software artifacts (libraries the user adopts or watches) are tracked in a
# parallel set of tables — see docs/ecosystem.md. They are deliberately kept
# separate from `items` (one-shot papers): an artifact is a long-lived entity
# that is re-polled and emits a stream of dated events.


class Artifact(Base):
    """A software project tracked across one or more package ecosystems."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), index=True)
    capability: Mapped[str] = mapped_column(String(30), index=True)
    tracks_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    homepage_url: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    first_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    refs: Mapped[list[ArtifactRef]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )
    events: Mapped[list[ArtifactEvent]] = relationship(back_populates="artifact")
    decisions: Mapped[list[ArtifactDecision]] = relationship(back_populates="artifact")


class ArtifactRef(Base):
    """One ecosystem reference of an artifact (a GitHub repo, a package, ...)."""

    __tablename__ = "artifact_refs"
    __table_args__ = (UniqueConstraint("ecosystem", "ref", name="uq_artifact_ref_ecosystem_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    ecosystem: Mapped[str] = mapped_column(String(20), index=True)
    ref: Mapped[str] = mapped_column(String(240))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    artifact: Mapped[Artifact] = relationship(back_populates="refs")
    state: Mapped[ArtifactState | None] = relationship(
        back_populates="artifact_ref", uselist=False, cascade="all, delete-orphan"
    )


class ArtifactState(Base):
    """Last-seen version per ecosystem ref — the diff baseline (no history)."""

    __tablename__ = "artifact_state"
    __table_args__ = (UniqueConstraint("artifact_ref_id", name="uq_artifact_state_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_ref_id: Mapped[int] = mapped_column(ForeignKey("artifact_refs.id"), index=True)
    last_version: Mapped[str | None] = mapped_column(String(120))
    last_release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(20), default="ok")
    last_error: Mapped[str] = mapped_column(Text, default="")
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    artifact_ref: Mapped[ArtifactRef] = relationship(back_populates="state")


class ArtifactEvent(Base):
    """A dated release / version change. Deduped on (ref, type, version)."""

    __tablename__ = "artifact_events"
    __table_args__ = (
        UniqueConstraint(
            "artifact_ref_id",
            "event_type",
            "version",
            name="uq_artifact_event_ref_type_version",
        ),
        Index("ix_artifact_event_artifact_date", "artifact_id", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    artifact_ref_id: Mapped[int] = mapped_column(ForeignKey("artifact_refs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[str | None] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="low", index=True)
    relevant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    matched_keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    artifact: Mapped[Artifact] = relationship(back_populates="events")
    artifact_ref: Mapped[ArtifactRef] = relationship()


class ArtifactDecision(Base):
    """Curator ring assignment for an artifact. Append-only, latest-wins."""

    __tablename__ = "artifact_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"), index=True)
    ring: Mapped[str] = mapped_column(String(40), index=True)
    tracks_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(120), default="")
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    previous_ring: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    artifact: Mapped[Artifact] = relationship(back_populates="decisions")
