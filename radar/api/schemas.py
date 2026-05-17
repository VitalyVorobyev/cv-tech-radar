from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from radar.schemas import RadarRing

Movement = Literal["new", "in", "out"]


class HealthResponse(BaseModel):
    ok: bool
    version: str


class CandidateScoresOut(BaseModel):
    relevance: float
    source_priority: float
    implementation: float
    attention: float
    novelty: float
    negative_penalty: float
    final: float


class CurrentDecisionOut(BaseModel):
    id: int
    ring: str
    reason: str
    action: str
    tracks: list[str]
    uncertain: bool
    decided_by: str
    created_at: datetime


class LLMJudgmentOut(BaseModel):
    verdict: str  # "yes" | "no" | "unknown"
    model: str
    reason: str
    judged_at: datetime


class CandidateOut(BaseModel):
    id: int
    type: str
    title: str
    abstract: str
    url: str
    pdf_url: str | None
    source: str
    published_at: datetime
    tracks: list[str]
    scores: CandidateScoresOut
    ring_suggested: RadarRing
    pipeline_rationale: str
    current_decision: CurrentDecisionOut | None = None
    llm_judgment: LLMJudgmentOut | None = None


class QueueResponse(BaseModel):
    date: str
    candidates: list[CandidateOut]


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    ring: RadarRing
    reason: str = Field(min_length=1)
    action: str = ""
    tracks: list[str] | None = None
    uncertain: bool = False
    decided_by: str = "web-curator"


class DecisionCreatedOut(BaseModel):
    decision_id: int
    created_at: datetime


class DecisionItemRef(BaseModel):
    id: int
    title: str
    url: str


class DecisionOut(BaseModel):
    item_id: int
    item: DecisionItemRef
    ring: str
    tracks: list[str]
    reason: str
    action: str
    uncertain: bool
    decided_by: str
    created_at: datetime


class DecisionListResponse(BaseModel):
    rows: list[DecisionOut]


class DigestItemOut(BaseModel):
    item_id: int
    title: str
    url: str
    tracks: list[str]
    reason: str
    action: str
    uncertain: bool
    ring: str
    decided_by: str
    created_at: datetime


class DigestSectionsOut(BaseModel):
    Use: list[DigestItemOut] = Field(default_factory=list)
    Prototype: list[DigestItemOut] = Field(default_factory=list)
    Evaluate: list[DigestItemOut] = Field(default_factory=list)
    Watch: list[DigestItemOut] = Field(default_factory=list)
    Ignore: list[DigestItemOut] = Field(default_factory=list)
    Uncertainty: list[DigestItemOut] = Field(default_factory=list)


class DigestResponse(BaseModel):
    date: str
    days: int
    sections: DigestSectionsOut


class BoardItemOut(BaseModel):
    item_id: int
    title: str
    url: str
    tracks: list[str]
    reason: str
    action: str
    uncertain: bool
    ring: str
    decided_by: str
    decided_at: datetime
    score: float | None = None
    llm_judgment: LLMJudgmentOut | None = None
    movement: Movement | None = None


class BoardRingsOut(BaseModel):
    Use: list[BoardItemOut] = Field(default_factory=list)
    Prototype: list[BoardItemOut] = Field(default_factory=list)
    Evaluate: list[BoardItemOut] = Field(default_factory=list)
    Watch: list[BoardItemOut] = Field(default_factory=list)
    Ignore: list[BoardItemOut] = Field(default_factory=list)


class BoardCountsOut(BaseModel):
    Use: int = 0
    Prototype: int = 0
    Evaluate: int = 0
    Watch: int = 0
    Ignore: int = 0


class BoardResponse(BaseModel):
    rings: BoardRingsOut
    counts: BoardCountsOut
    decided_since: datetime | None = None
    include_ignore: bool = False


class TrackOut(BaseModel):
    id: str
    name: str
    quadrant: str


class TracksResponse(BaseModel):
    tracks: list[TrackOut]


class SourceOut(BaseModel):
    id: str
    name: str
    kind: str
    enabled: bool
    priority: int


class SourcesResponse(BaseModel):
    sources: list[SourceOut]


class HistoryEntryOut(BaseModel):
    ring: str
    at: datetime


class ItemDetailOut(BaseModel):
    id: int
    title: str
    abstract: str
    url: str
    ring: str
    track: str
    tracks: list[str]
    reason: str
    uncertain: bool
    source: str
    published_at: datetime
    decided_at: datetime
    decided_by: str | None
    history: list[HistoryEntryOut]
    movement: Movement | None


class TimelineWeekOut(BaseModel):
    iso: str
    label: str
    Use: int = 0
    Prototype: int = 0
    Evaluate: int = 0
    Watch: int = 0
    Ignore: int = 0


class TimelineResponse(BaseModel):
    weeks: list[TimelineWeekOut]


# --- Ecosystem monitoring ---------------------------------------------------


class EcosystemLatestEvent(BaseModel):
    event_type: str
    version: str | None
    event_date: datetime
    summary: str
    url: str


class ArtifactBoardItem(BaseModel):
    artifact_id: int
    key: str
    name: str
    description: str
    status: str
    ring: str
    capability: str
    tracks: list[str] = Field(default_factory=list)
    ecosystems: list[str] = Field(default_factory=list)
    latest_event: EcosystemLatestEvent | None = None
    recent_event_count: int = 0
    decided_at: datetime | None = None
    movement: Movement | None = None


class EcosystemBoardRingsOut(BaseModel):
    Use: list[ArtifactBoardItem] = Field(default_factory=list)
    Prototype: list[ArtifactBoardItem] = Field(default_factory=list)
    Evaluate: list[ArtifactBoardItem] = Field(default_factory=list)
    Watch: list[ArtifactBoardItem] = Field(default_factory=list)
    Ignore: list[ArtifactBoardItem] = Field(default_factory=list)


class EcosystemBoardResponse(BaseModel):
    rings: EcosystemBoardRingsOut
    counts: BoardCountsOut
    include_ignore: bool = False


class EcosystemEventItem(BaseModel):
    id: int
    artifact_id: int
    artifact_key: str
    artifact_name: str
    ecosystem: str
    event_type: str
    version: str | None
    event_date: datetime
    summary: str
    body: str
    url: str
    severity: str
    relevant: bool
    matched_keywords: list[str] = Field(default_factory=list)


class EcosystemEventsResponse(BaseModel):
    date: str
    days: int
    events: list[EcosystemEventItem] = Field(default_factory=list)


class ArtifactRefDetail(BaseModel):
    ecosystem: str
    ref: str
    last_version: str | None = None
    last_release_at: datetime | None = None
    last_status: str
    last_checked_at: datetime | None = None


class ArtifactDecisionEntry(BaseModel):
    ring: str
    tracks: list[str] = Field(default_factory=list)
    reason: str
    action: str
    decided_by: str
    uncertain: bool
    decided_at: datetime


class ArtifactDetailResponse(BaseModel):
    artifact_id: int
    key: str
    name: str
    description: str
    status: str
    capability: str
    homepage_url: str
    ring: str
    tracks: list[str] = Field(default_factory=list)
    refs: list[ArtifactRefDetail] = Field(default_factory=list)
    events: list[EcosystemEventItem] = Field(default_factory=list)
    decisions: list[ArtifactDecisionEntry] = Field(default_factory=list)


class ArtifactDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: int
    ring: RadarRing
    reason: str = Field(min_length=1)
    action: str = ""
    tracks: list[str] | None = None
    uncertain: bool = False
    decided_by: str = "web-curator"


class ArtifactDecisionCreatedOut(BaseModel):
    decision_id: int
    created_at: datetime
