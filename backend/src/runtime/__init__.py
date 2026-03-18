"""
Runtime dependency wiring for v3 — shared by API and worker.

Use this module when you need v3 repos or clock without depending on the API layer.
API dependencies import from here; worker imports from here.
"""

from src.runtime.v3_deps import (
    get_aisle_repo,
    get_clock,
    get_evidence_repo,
    get_inventory_repo,
    get_inventory_visual_reference_repo,
    get_job_repo,
    get_position_repo,
    get_product_record_repo,
    get_source_asset_repo,
)

__all__ = [
    "get_aisle_repo",
    "get_clock",
    "get_evidence_repo",
    "get_inventory_repo",
    "get_inventory_visual_reference_repo",
    "get_job_repo",
    "get_position_repo",
    "get_product_record_repo",
    "get_source_asset_repo",
]
