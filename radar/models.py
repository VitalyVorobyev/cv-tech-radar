from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped[Item] = relationship(back_populates="decisions")


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(Text)
    markdown_path: Mapped[str] = mapped_column(Text)
    json_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
