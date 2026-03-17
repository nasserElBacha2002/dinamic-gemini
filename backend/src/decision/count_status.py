"""
Count status assignment for v2.1 entities.

EMPTY_PALLET → EMPTY, final_quantity=0
LOOSE_BOXES: depends on product evidence (not automatic INVALID_STRUCTURE).
  - conflict_flag set → NEEDS_REVIEW
  - Has identity (position_barcode or internal_code) and valid quantity (>0) → COUNTED
  - Has identity or valid quantity (partial) → NEEDS_REVIEW
  - No identity and no valid quantity → INVALID_STRUCTURE
PALLET: position+product_qty → COUNTED; partial → NEEDS_REVIEW; none → NOT_COUNTABLE
If conflict_flag already set (duplicate barcode), keep NEEDS_REVIEW.
"""

from src.domain.entity import Entity


def _has_position(e: Entity) -> bool:
    """True if entity has position (barcode)."""
    return bool(e.position_barcode and e.position_barcode.strip())


def _has_identity(e: Entity) -> bool:
    """True if entity has an identifier (position barcode or product/SKU)."""
    return bool(
        (e.position_barcode and e.position_barcode.strip())
        or (e.internal_code and e.internal_code.strip())
    )


def _has_valid_product_qty(e: Entity) -> bool:
    """True if entity has a valid product quantity (present and > 0)."""
    return e.product_label_quantity is not None and e.product_label_quantity > 0


def assign_count_status(entity: Entity) -> None:
    """Set count_status and final_quantity per entity type and signals. Mutates entity."""
    if entity.entity_type == "EMPTY_PALLET":
        entity.count_status = "EMPTY"
        entity.final_quantity = 0
        return

    if entity.entity_type == "LOOSE_BOXES":
        if entity.conflict_flag:
            entity.count_status = "NEEDS_REVIEW"
            entity.final_quantity = None
            return
        has_identity = _has_identity(entity)
        has_qty = _has_valid_product_qty(entity)
        if has_identity and has_qty:
            entity.count_status = "COUNTED"
            entity.final_quantity = entity.product_label_quantity
        elif has_identity or has_qty:
            entity.count_status = "NEEDS_REVIEW"
            entity.final_quantity = None
        else:
            entity.count_status = "INVALID_STRUCTURE"
            entity.final_quantity = None
        return

    if entity.entity_type == "PALLET":
        if entity.conflict_flag:
            entity.count_status = "NEEDS_REVIEW"
            entity.final_quantity = None
            return
        has_pos = _has_position(entity)
        has_qty = entity.product_label_quantity is not None
        if has_pos and has_qty:
            entity.count_status = "COUNTED"
            entity.final_quantity = entity.product_label_quantity
        elif has_pos or has_qty:
            entity.count_status = "NEEDS_REVIEW"
            entity.final_quantity = None
        else:
            entity.count_status = "NOT_COUNTABLE"
            entity.final_quantity = None
        return

    entity.count_status = "NOT_COUNTABLE"
    entity.final_quantity = None
