"""v3 API main router: single prefix, domain-based sub-routers."""

from fastapi import APIRouter

from . import inventories, aisles, assets, positions, reviews

router = APIRouter(prefix="/api/v3/inventories", tags=["inventories-v3"])

router.include_router(inventories.router)
router.include_router(aisles.router)
router.include_router(assets.router)
router.include_router(positions.router)
router.include_router(reviews.router)
