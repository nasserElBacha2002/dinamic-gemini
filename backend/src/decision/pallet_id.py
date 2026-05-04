"""
Deterministic pallet_id resolution for v2.1.

Priority: position_barcode → generated PALLET_001...
(position_label_text no se pide a Gemini para reducir coste/tokens.)
Duplicate position_barcode: conflict_flag, DUPLICATE_POSITION_BARCODE; no suffix.
"""

from src.domain.entity import Entity


def _has_position_barcode(e: Entity) -> bool:
    """True if position_barcode is non-null and non-empty."""
    return bool(e.position_barcode and e.position_barcode.strip())


def resolve_pallet_id(entities: list[Entity]) -> None:
    """Resolve pallet_id and pallet_id_method for each entity. Mutates in place.

    Priority:
    1. position_barcode (if valid). If two PALLET entities share same barcode:
       set both conflict_flag=True, conflict_reason=DUPLICATE_POSITION_BARCODE,
       count_status=NEEDS_REVIEW, pallet_id=position_barcode (no suffix).
    2. Generated PALLET_001, PALLET_002, ... in sorted order (call after sort_entities_deterministically).

    Ensures generated IDs are unique.
    """
    barcode_to_indices: dict = {}
    for i, e in enumerate(entities):
        if e.entity_type != "PALLET":
            e.pallet_id = None
            e.pallet_id_method = None
            continue
        if _has_position_barcode(e):
            e.pallet_id = (e.position_barcode or "").strip()
            e.pallet_id_method = "position_barcode"
            key = e.pallet_id
            if key not in barcode_to_indices:
                barcode_to_indices[key] = []
            barcode_to_indices[key].append(i)
        else:
            e.pallet_id = None
            e.pallet_id_method = None

    for key, indices in barcode_to_indices.items():
        if len(indices) > 1:
            for i in indices:
                entities[i].conflict_flag = True
                entities[i].conflict_reason = "DUPLICATE_POSITION_BARCODE"

    counter = 1
    for e in entities:
        if e.entity_type != "PALLET":
            continue
        if e.pallet_id is not None and e.pallet_id_method is not None:
            continue
        e.pallet_id = f"PALLET_{counter:03d}"
        e.pallet_id_method = "generated"
        counter += 1
