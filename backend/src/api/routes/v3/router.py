"""v3 API main router: single prefix, domain-based sub-routers.

v3.2.1 Phase 3: all v3 business routes require authentication via router-level
dependency; auth failures return the stable AuthHttpError contract.
"""

from fastapi import APIRouter, Depends

from src.api.constants.route_paths import API_V3_INVENTORIES_ROUTER_PREFIX
from src.auth.dependencies import get_current_admin

from . import (
    aisles,
    assets,
    authoritative_aisle_finalization,
    authoritative_local_code_scan,
    capture_sessions,
    code_scans,
    image_results,
    inventories,
    positions,
    preliminary_detections,
    preliminary_reconciliations,
    processing_observability,
    reviews,
)

router = APIRouter(
    prefix=API_V3_INVENTORIES_ROUTER_PREFIX,
    tags=["inventories-v3"],
    dependencies=[Depends(get_current_admin)],
)

router.include_router(inventories.router)
router.include_router(capture_sessions.router)
router.include_router(aisles.router)
router.include_router(code_scans.router)
router.include_router(assets.router)
router.include_router(authoritative_local_code_scan.router)
router.include_router(authoritative_aisle_finalization.router)
router.include_router(preliminary_detections.router)
router.include_router(preliminary_reconciliations.router)
router.include_router(positions.router)
router.include_router(image_results.router)
router.include_router(processing_observability.router)
router.include_router(reviews.router)
