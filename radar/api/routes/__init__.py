from __future__ import annotations

from fastapi import APIRouter

from radar.api.routes.board import router as board_router
from radar.api.routes.decisions import router as decisions_router
from radar.api.routes.digest import router as digest_router
from radar.api.routes.items import router as items_router
from radar.api.routes.meta import router as meta_router
from radar.api.routes.queue import router as queue_router
from radar.api.routes.timeline import router as timeline_router

router = APIRouter(prefix="/api")
router.include_router(queue_router)
router.include_router(decisions_router)
router.include_router(digest_router)
router.include_router(board_router)
router.include_router(meta_router)
router.include_router(items_router)
router.include_router(timeline_router)

__all__ = ["router"]
