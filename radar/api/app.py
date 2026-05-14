from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from radar.api.deps import configure
from radar.api.routes import router as api_router

DEV_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)
FRONTEND_DIST_DIR = Path("frontend/dist")


def create_app(
    db_path: Path | None = None,
    config_dir: Path | None = None,
    *,
    frontend_dist: Path | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``db_path`` and ``config_dir`` configure where the API reads its state
    from. ``frontend_dist`` overrides the default ``frontend/dist`` static
    mount location; if the directory does not exist the static mount is
    skipped, keeping backend-only deployments and tests lightweight.
    """
    configure(db_path=db_path, config_dir=config_dir)

    app = FastAPI(title="CV Tech Radar", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    dist_dir = Path(frontend_dist) if frontend_dist is not None else FRONTEND_DIST_DIR
    _mount_frontend(app, dist_dir)

    return app


def _mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    if not dist_dir.exists() or not dist_dir.is_dir():
        return

    assets_dir = dist_dir / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    index_file = dist_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(request: Request, full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")

        target = dist_dir / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        if index_file.is_file():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="frontend not built")


def _app_for_reload() -> FastAPI:
    """Factory used by ``uvicorn --reload``.

    Picks up settings from ``CV_RADAR_DB_PATH`` and ``CV_RADAR_CONFIG_DIR``
    environment variables so the reloader can spawn fresh worker processes.
    """
    db_env = os.environ.get("CV_RADAR_DB_PATH")
    config_env = os.environ.get("CV_RADAR_CONFIG_DIR")
    return create_app(
        db_path=Path(db_env) if db_env else None,
        config_dir=Path(config_env) if config_env else None,
    )
