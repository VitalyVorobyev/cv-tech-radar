from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from radar.schemas import RadarRing


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


class BoardRingsOut(BaseModel):
    Use: list[DigestItemOut] = Field(default_factory=list)
    Prototype: list[DigestItemOut] = Field(default_factory=list)
    Evaluate: list[DigestItemOut] = Field(default_factory=list)
    Watch: list[DigestItemOut] = Field(default_factory=list)
    Ignore: list[DigestItemOut] = Field(default_factory=list)


class BoardResponse(BaseModel):
    rings: BoardRingsOut


class TrackOut(BaseModel):
    id: str
    name: str


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
