"""
Entity quality score (local, deterministic) for v2.1.

Formula: base = confidence; +0.2 if position; +0.3 if product_label_quantity; +0.1 if PALLET and has_boxes.
Clamp [0, 1].

NOTE:
+0.1 currently uses has_boxes because Stage 2.1.B (barcode hardening)
is not implemented yet. When barcode hardening is added, this
term should instead reflect locally confirmed barcodes.
"""

from src.domain.entity import Entity


def _has_position(e: Entity) -> bool:
    return bool(e.position_barcode and e.position_barcode.strip())


def compute_entity_quality_score(entity: Entity) -> float:
    """Compute entity_quality_score and set it on entity. Returns the score.

    Formula:
    - base = confidence
    - +0.2 if position_barcode exists
    - +0.3 if product_label_quantity exists
    - +0.1 if entity_type == PALLET and has_boxes == True
    - clamp between 0 and 1
    """
    base = entity.confidence
    if _has_position(entity):
        base += 0.2
    if entity.product_label_quantity is not None:
        base += 0.3
    if entity.entity_type == "PALLET" and entity.has_boxes:
        base += 0.1
    score = max(0.0, min(1.0, base))
    entity.entity_quality_score = score
    return score
