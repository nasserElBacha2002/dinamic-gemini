"""
Optional prompt fragments appended **after** ``HybridPromptComposer.compose_base`` (Epic 3.1.A / D).

The composer returns base text only; the hybrid pipeline (e.g. ``hybrid_analysis_prompt``) applies
these helpers explicitly. Do not call them from inside ``compose_base`` — avoids double-append and
keeps enrichment policy at the request-building layer.
"""

from __future__ import annotations

from src.domain.execution_image_manifest import EVIDENCE_RETURN_IDENTIFIER_FIELD, ExecutionImageManifest, ExecutionImageRole
from src.jobs.image_identity import JobImage

# Traceability id for Phase 6 metadata (when ``enrich_prompt_with_image_ids`` applies).
IMAGE_ID_TRACEABILITY_ENRICHMENT_ID = "image_id_traceability_v31"
# Phase E4: supplier-editable block appended after protected hybrid + optional image IDs (metadata only).
SUPPLIER_EDITABLE_INSTRUCTIONS_ENRICHMENT_ID = "supplier_editable_instructions_e4"

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
    images: list[JobImage],
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


def enrich_prompt_with_sent_image_ids(
    base_prompt: str,
    images: list[JobImage],
    sent_image_ids: list[str],
) -> str:
    """
    Append traceability list for primary evidence frames actually sent to the model (Phase 1).

    Preserves every ID in ``sent_image_ids`` in order. IDs without ``JobImage`` metadata use
    the ID-only line format.
    """
    if not sent_image_ids:
        return base_prompt
    by_id = {img.image_id: img for img in images}
    lines = ["\n\nInput images (use these exact IDs as source_image_id per result):"]
    for image_id in sent_image_ids:
        img = by_id.get(image_id)
        if img is not None:
            lines.append(
                f"- {img.image_id} (upload_order={img.upload_order}, "
                f"original_filename={img.original_filename!r})"
            )
        else:
            lines.append(f"- {image_id}")
    block = "\n".join(lines)
    return base_prompt.rstrip() + "\n" + block + _TRACEABILITY_INSTRUCTION


def enrich_prompt_with_image_id_strings(
    base_prompt: str,
    image_ids: list[str],
) -> str:
    """Append ID-only list when JobImage metadata is unavailable for sent frames."""
    if not image_ids:
        return base_prompt
    lines = ["\n\nInput images (use these exact IDs as source_image_id per result):"]
    for image_id in image_ids:
        lines.append(f"- {image_id}")
    block = "\n".join(lines)
    return base_prompt.rstrip() + "\n" + block + _TRACEABILITY_INSTRUCTION


_MANIFEST_TRACEABILITY_INSTRUCTION: str = """

TRACEABILITY (Phase 4.3): Only PRIMARY EVIDENCE images may be returned as {field}.
REFERENCE images are classification context only — never use them as evidence.
Return the exact {field} from the PRIMARY EVIDENCE section for each result.
""".format(field=EVIDENCE_RETURN_IDENTIFIER_FIELD)


def enrich_prompt_with_execution_manifest(
    base_prompt: str,
    manifest: ExecutionImageManifest,
) -> str:
    """Append canonical manifest sections for model-facing image identity (Phase 4.3)."""
    primary_lines: list[str] = []
    reference_lines: list[str] = []
    for entry in manifest.ordered_entries():
        fname = f", filename={entry.original_filename!r}" if entry.original_filename else ""
        line = (
            f"- {entry.manifest_entry_id} "
            f"(source_image_id={entry.source_image_id!r}{fname})"
        )
        if entry.role == ExecutionImageRole.PRIMARY_EVIDENCE:
            primary_lines.append(line)
        else:
            reference_lines.append(line)

    sections = ["\n\nPRIMARY EVIDENCE IMAGES"]
    sections.extend(primary_lines or ["- (none)"])
    if reference_lines:
        sections.append("\nREFERENCE IMAGES (classification context only)")
        sections.extend(reference_lines)
    block = "\n".join(sections)
    return base_prompt.rstrip() + "\n" + block + _MANIFEST_TRACEABILITY_INSTRUCTION
