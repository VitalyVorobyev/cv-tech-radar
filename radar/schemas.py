from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class RadarRing(StrEnum):
    USE = "Use"
    PROTOTYPE = "Prototype"
    EVALUATE = "Evaluate"
    WATCH = "Watch"
    IGNORE = "Ignore"


class ItemType(StrEnum):
    PAPER = "paper"
    BLOG_POST = "blog_post"
    VENDOR_NEWS = "vendor_news"
    LIBRARY_RELEASE = "library_release"
    STANDARD_UPDATE = "standard_update"
    DATASET = "dataset"
    BENCHMARK = "benchmark"
    CONFERENCE_ITEM = "conference_item"
    GITHUB_REPO = "github_repo"
    ATLAS_CANDIDATE = "atlas_candidate"


class SourceConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["arxiv", "rss", "manual"]
    url: HttpUrl
    enabled: bool = True
    priority: int = Field(default=0, ge=0, le=5)
    notes: str = ""
    categories: list[str] = Field(default_factory=list)

    @field_validator("categories")
    @classmethod
    def arxiv_sources_need_categories(cls, categories: list[str], info) -> list[str]:
        if info.data.get("kind") == "arxiv" and not categories:
            msg = "arXiv sources must define at least one category"
            raise ValueError(msg)
        return categories


class SourcesConfig(BaseModel):
    sources: list[SourceConfig]

    @model_validator(mode="after")
    def source_ids_are_unique(self) -> SourcesConfig:
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            msg = "source ids must be unique"
            raise ValueError(msg)
        return self


class TrackConfig(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    positive_keywords: list[str] = Field(min_length=1)
    negative_keywords: list[str] = Field(default_factory=list)


class TopicsConfig(BaseModel):
    tracks: list[TrackConfig]

    @model_validator(mode="after")
    def track_ids_are_unique(self) -> TopicsConfig:
        ids = [track.id for track in self.tracks]
        if len(ids) != len(set(ids)):
            msg = "track ids must be unique"
            raise ValueError(msg)
        return self


class NegativeTopicsConfig(BaseModel):
    negative_topics: list[str] = Field(default_factory=list)


class PrioritySourcesConfig(BaseModel):
    organizations: dict[str, list[str]] = Field(default_factory=dict)
    vendors: dict[str, list[str]] = Field(default_factory=dict)


class ScoreWeights(BaseModel):
    relevance: float = Field(ge=0)
    source_priority: float = Field(ge=0)
    implementation: float = Field(ge=0)
    attention: float = Field(ge=0)
    novelty: float = Field(ge=0)
    negative_penalty: float = Field(ge=0)


class ScoreThresholds(BaseModel):
    use: int = Field(ge=0, le=100)
    prototype: int = Field(ge=0, le=100)
    evaluate: int = Field(ge=0, le=100)
    watch: int = Field(ge=0, le=100)
    ignore: int = Field(ge=0, le=100)


class ScoringConfig(BaseModel):
    weights: ScoreWeights
    thresholds: ScoreThresholds
    source_priority_cap: int = Field(default=60, ge=0, le=100)
    candidate_limit: int = Field(default=25, ge=1, le=500)

    @model_validator(mode="after")
    def thresholds_descend(self) -> ScoringConfig:
        values = self.thresholds
        if not (values.use >= values.prototype >= values.evaluate >= values.watch >= values.ignore):
            msg = "thresholds must descend from use to ignore"
            raise ValueError(msg)
        return self


class EmbeddingsSettings(BaseModel):
    enabled: bool = False
    provider: Literal["ollama"] = "ollama"
    model: str = "embeddinggemma:latest"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = Field(default=30, ge=1)
    near_duplicate_threshold: float = Field(default=0.92, ge=0.0, le=1.0)


class ChatSettings(BaseModel):
    enabled: bool = False
    provider: Literal["ollama"] = "ollama"
    model: str = "gemma4:e2b"
    base_url: str = "http://localhost:11434"
    timeout_seconds: int = Field(default=60, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    # Reasoning-style models (e.g. gemma4:e2b) burn most of num_predict on
    # internal reasoning before emitting any visible output. A single judging
    # call with the strict yes/no prompt observed ~400 total output tokens on
    # gemma4:e2b; 2048 leaves comfortable headroom. Lower this only for
    # non-reasoning models.
    max_tokens: int = Field(default=2048, ge=1)


class EmbeddingsConfig(BaseModel):
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)


class AppConfig(BaseModel):
    sources: SourcesConfig
    topics: TopicsConfig
    negative_topics: NegativeTopicsConfig
    priority_sources: PrioritySourcesConfig
    scoring: ScoringConfig
    embeddings: EmbeddingsConfig


class NormalizedItem(BaseModel):
    type: ItemType
    title: str
    abstract_or_summary: str
    url: str
    pdf_url: str | None = None
    published_at: datetime
    updated_at: datetime | None = None
    source_name: str
    external_id: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ClassificationResult(BaseModel):
    tracks: list[str]
    positive_keywords: list[str]
    negative_keywords: list[str]
    relevance_score: float
    novelty_score: float
    source_priority_score: float
    implementation_score: float
    attention_score: float
    final_score: float
    negative_topic_penalty: float
    recommended_ring: RadarRing
    confidence: float
    rationale: str


class CandidateScores(BaseModel):
    relevance: float
    source_priority: float
    implementation: float
    attention: float
    novelty: float
    negative_penalty: float
    final: float


class CandidateRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: int
    type: ItemType
    title: str
    url: str
    pdf_url: str | None
    published_at: datetime
    source: str
    external_id: str | None
    authors: list[str]
    tracks: list[str]
    ring: RadarRing
    scores: CandidateScores
    summary: str
    pipeline_rationale: str


class DecisionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ring: RadarRing
    reason: str = Field(min_length=1)
    action: str = ""
    tracks: list[str] | None = None
    uncertain: bool = False
