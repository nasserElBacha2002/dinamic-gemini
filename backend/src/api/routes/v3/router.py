"""v3 API main router: single prefix, domain-based sub-routers.

v3.2.1 Phase 3: all v3 business routes require authentication via router-level
dependency; auth failures return the stable AuthHttpError contract.
"""

from fastapi import APIRouter, Depends

from src.api.constants.route_paths import API_V3_INVENTORIES_ROUTER_PREFIX
from src.auth.dependencies import get_current_admin

from . import inventories, aisles, assets, positions, reviews

router = APIRouter(
    prefix=API_V3_INVENTORIES_ROUTER_PREFIX,
    tags=["inventories-v3"],
    dependencies=[Depends(get_current_admin)],
)

router.include_router(inventories.router)
router.include_router(aisles.router)
router.include_router(assets.router)
router.include_router(positions.router)
router.include_router(reviews.router)
