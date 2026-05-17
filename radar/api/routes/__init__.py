from __future__ import annotations

from fastapi import APIRouter

from radar.api.routes.board import router as board_router
from radar.api.routes.candidates import router as candidates_router
from radar.api.routes.config import router as config_router
from radar.api.routes.decisions import router as decisions_router
from radar.api.routes.digest import router as digest_router
from radar.api.routes.ecosystem import router as ecosystem_router
from radar.api.routes.items import router as items_router
from radar.api.routes.jobs import router as jobs_router
from radar.api.routes.manual import router as manual_router
from radar.api.routes.meta import router as meta_router
from radar.api.routes.near_duplicates import router as near_duplicates_router
from radar.api.routes.ollama import router as ollama_router
from radar.api.routes.queue import router as queue_router
from radar.api.routes.score_debug import router as score_debug_router
from radar.api.routes.timeline import router as timeline_router

router = APIRouter(prefix="/api")
router.include_router(queue_router)
router.include_router(decisions_router)
router.include_router(digest_router)
router.include_router(board_router)
router.include_router(ecosystem_router)
router.include_router(meta_router)
router.include_router(items_router)
router.include_router(manual_router)
router.include_router(timeline_router)
router.include_router(candidates_router)
router.include_router(config_router)
router.include_router(jobs_router)
router.include_router(score_debug_router)
router.include_router(near_duplicates_router)
router.include_router(ollama_router)

__all__ = ["router"]
