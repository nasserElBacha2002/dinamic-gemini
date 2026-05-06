"""
Stage 4 — Assign processing mode and final_quantity per pallet.

Rules:
- label: has_label and internal_code and quantity present → use quantity.
- visual_fallback: otherwise → use estimated_visible_boxes (can be None).
"""

from dataclasses import replace

from src.domain.pallet import Pallet


def assign_processing_mode(pallet: Pallet) -> Pallet:
    """Assign processing_mode, source, and final_quantity from pallet data.

    Rules:
    - If pallet.has_label is True AND internal_code is not None AND quantity is not None:
        processing_mode = "label", source = "label", final_quantity = quantity.
    - Else:
        processing_mode = "visual_fallback", source = "visual_fallback",
        final_quantity = estimated_visible_boxes (can be None).

    fallback_used remains False (Stage 6 may set True when fallback counting is used).

    Args:
        pallet: Parsed pallet (parser leaves processing_mode/final_quantity/source unset).

    Returns:
        New Pallet with processing_mode, source, final_quantity, fallback_used set.
    """
    if pallet.has_label and pallet.internal_code is not None and pallet.quantity is not None:
        return replace(
            pallet,
            processing_mode="label",
            source="label",
            final_quantity=pallet.quantity,
            fallback_used=False,
        )
    return replace(
        pallet,
        processing_mode="visual_fallback",
        source="visual_fallback",
        final_quantity=pallet.estimated_visible_boxes,
        fallback_used=False,
    )
