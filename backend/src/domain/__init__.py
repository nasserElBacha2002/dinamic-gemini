"""Dominio v2.0 (Pallet), v2.1 (Entity) y v3.0 (Inventory, Aisle, Position, etc.)."""

# V3.0 domain (Documento técnico §7)
from src.domain.aisle import Aisle, AisleStatus
from src.domain.assets import SourceAsset, SourceAssetType
from src.domain.entity import Entity
from src.domain.evidence import Evidence, EvidenceType
from src.domain.inventory import Inventory, InventoryStatus
from src.domain.jobs import Job, JobStatus
from src.domain.pallet import Pallet
from src.domain.positions import Position, PositionStatus
from src.domain.products import ProductRecord
from src.domain.reviews import ReviewAction, ReviewActionType

__all__ = [
    "Aisle",
    "AisleStatus",
    "Entity",
    "Evidence",
    "EvidenceType",
    "Inventory",
    "InventoryStatus",
    "Job",
    "JobStatus",
    "Pallet",
    "Position",
    "PositionStatus",
    "ProductRecord",
    "ReviewAction",
    "ReviewActionType",
    "SourceAsset",
    "SourceAssetType",
]
