from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from radar.api.deps import get_config, get_session
from radar.api.schemas import (
    HealthResponse,
    SourceOut,
    SourcesResponse,
    TrackOut,
    TracksResponse,
)
from radar.models import Source
from radar.schemas import AppConfig

router = APIRouter(tags=["meta"])


def _package_version() -> str:
    try:
        return version("cv-radar")
    except PackageNotFoundError:
        return "0.0.0"


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    return HealthResponse(ok=True, version=_package_version())


@router.get("/tracks", response_model=TracksResponse)
def get_tracks(config: Annotated[AppConfig, Depends(get_config)]) -> TracksResponse:
    return TracksResponse(
        tracks=[
            TrackOut(id=track.id, name=track.name, quadrant=track.quadrant)
            for track in config.topics.tracks
        ]
    )


@router.get("/sources", response_model=SourcesResponse)
def get_sources(session: Annotated[Session, Depends(get_session)]) -> SourcesResponse:
    rows = session.scalars(select(Source).order_by(Source.priority.desc(), Source.name)).all()
    return SourcesResponse(
        sources=[
            SourceOut(
                id=row.key,
                name=row.name,
                kind=row.kind,
                enabled=bool(row.enabled),
                priority=int(row.priority),
            )
            for row in rows
        ]
    )
