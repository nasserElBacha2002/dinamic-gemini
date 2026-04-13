"""
Optional prompt fragments appended **after** ``HybridPromptComposer.compose_base`` (Epic 3.1.A / D).

The composer returns base text only; the hybrid pipeline (e.g. ``hybrid_analysis_prompt``) applies
these helpers explicitly. Do not call them from inside ``compose_base`` — avoids double-append and
keeps enrichment policy at the request-building layer.
"""

from __future__ import annotations

from typing import List

from src.jobs.image_identity import JobImage

# Traceability id for Phase 6 metadata (when ``enrich_prompt_with_image_ids`` applies).
IMAGE_ID_TRACEABILITY_ENRICHMENT_ID = "image_id_traceability_v31"

# Epic 3.1.A — image ID traceability
_TRACEABILITY_INSTRUCTION: str = """

TRACEABILITY (v3.1): Each input image has a unique identifier below. For every entity or counted result you return, you MUST include the exact source_image_id of the image used as evidence for that result. Do not invent IDs. Only use image IDs from the list below.
"""

# Epic 3.1.D — Product/label association
_PRODUCT_LABEL_ASSOCIATION: str = """


PRODUCT AND LABEL ASSOCIATION (v3.1.D): For each entity, use internal_code ONLY for the product/SKU code from the product label (the label on the boxes or product). Use position_barcode ONLY for the position or pallet barcode/label (location or pallet identifier). Do not mix them: internal_code = product identifier, position_barcode = position/pallet identifier.
"""


def enrich_prompt_with_product_label_association(base_prompt: str) -> str:
    """Append Epic 3.1.D product/label association instructions to the base prompt."""
    return base_prompt.rstrip() + _PRODUCT_LABEL_ASSOCIATION


def enrich_prompt_with_image_ids(
    base_prompt: str,
    images: List[JobImage],
) -> str:
    """Append image list and traceability instruction (Epic 3.1.A)."""
    if not images:
        return base_prompt
    lines = ["\n\nInput images (use these exact IDs as source_image_id per result):"]
    for img in images:
        lines.append(
            f"- {img.image_id} (upload_order={img.upload_order}, original_filename={img.original_filename!r})"
        )
    block = "\n".join(lines)
    return base_prompt.rstrip() + "\n" + block + _TRACEABILITY_INSTRUCTION
