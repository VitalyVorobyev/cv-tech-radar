"""REST endpoints for reading and writing radar config slices.

Every ``PUT`` route accepts the same Pydantic schema the rest of the app
uses (``SourcesConfig``, ``TopicsConfig``, ...). Pydantic does all of the
heavy-lifting validation: by the time a payload reaches the writer it is
already structurally valid, so the writer just dumps it back to disk
atomically and clears the config cache.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends

from radar.api.deps import get_config, get_settings
from radar.config_io import (
    reload_config,
    write_negative_topics,
    write_scoring,
    write_sources,
    write_topics,
)
from radar.schemas import (
    AppConfig,
    NegativeTopicsConfig,
    ScoringConfig,
    SourcesConfig,
    TopicsConfig,
)
from radar.utils import utc_now

router = APIRouter(prefix="/config", tags=["config"])


def _config_path(filename: str) -> Path:
    settings = get_settings()
    config_dir = settings.config_dir or Path("config")
    return config_dir / filename


def _saved_response(path) -> dict:
    return {"path": str(path), "saved_at": utc_now().isoformat()}


@router.get("/sources", response_model=SourcesConfig)
def get_sources_config(config: Annotated[AppConfig, Depends(get_config)]) -> SourcesConfig:
    return config.sources


@router.put("/sources")
def put_sources_config(payload: Annotated[SourcesConfig, Body()]) -> dict:
    path = write_sources(payload, path=_config_path("sources.yaml"))
    reload_config()
    return _saved_response(path)


@router.get("/topics", response_model=TopicsConfig)
def get_topics_config(config: Annotated[AppConfig, Depends(get_config)]) -> TopicsConfig:
    return config.topics


@router.put("/topics")
def put_topics_config(payload: Annotated[TopicsConfig, Body()]) -> dict:
    path = write_topics(payload, path=_config_path("topics.yaml"))
    reload_config()
    return _saved_response(path)


@router.get("/negative-topics", response_model=NegativeTopicsConfig)
def get_negative_topics_config(
    config: Annotated[AppConfig, Depends(get_config)],
) -> NegativeTopicsConfig:
    return config.negative_topics


@router.put("/negative-topics")
def put_negative_topics_config(
    payload: Annotated[NegativeTopicsConfig, Body()],
) -> dict:
    path = write_negative_topics(payload, path=_config_path("negative_topics.yaml"))
    reload_config()
    return _saved_response(path)


@router.get("/scoring", response_model=ScoringConfig)
def get_scoring_config(config: Annotated[AppConfig, Depends(get_config)]) -> ScoringConfig:
    return config.scoring


@router.put("/scoring")
def put_scoring_config(payload: Annotated[ScoringConfig, Body()]) -> dict:
    path = write_scoring(payload, path=_config_path("scoring.yaml"))
    reload_config()
    return _saved_response(path)


@router.post("/reload")
def post_reload() -> dict:
    reload_config()
    return {"reloaded_at": utc_now().isoformat()}
