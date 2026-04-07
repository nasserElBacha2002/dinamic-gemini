"""
Módulo unificado de prompts para Gemini API.

Todos los prompts viven en el diccionario PROMPTS. El pipeline híbrido usa
get_hybrid_prompt() con la variable de entorno HYBRID_PROMPT (default: global_v21).
Valores del diccionario: str (prompt único híbrido legacy), dict con claves
``default`` / ``openai`` (híbrido multi-proveedor), o dict con "system"/"user" (legacy).
"""

from typing import Dict, Final, List, Optional, Union

from src.jobs.image_identity import JobImage

# Textos base (referenciados por PROMPTS)
_GLOBAL_V21: Final[str] = """\
Analyze the provided warehouse aisle evidence (photos and/or extracted frames). Detect all distinct visible logistic entities, one entity per visible unit.

Entity types:
- PALLET: pallet structure, may have boxes and position/product labels.
- EMPTY_PALLET: pallet structure with no boxes on top.
- LOOSE_BOXES: non-palletized boxed units or grouped boxes without pallet structure (do NOT count as pallet).

Rules:
- Treat each clearly visible logistic unit as its own entity. If adjacent boxed units are visibly distinct, return them separately.
- If a visible unit has its own label or a clear visual boundary, prefer treating it as an individual entity.
- Do NOT collapse multiple labeled or clearly separable visible boxes into one entity.
- Do NOT duplicate, merge, or infer hidden entities.
- Do not invent values. Use null if not clearly readable.
- Do not return quantity 0 for a clearly visible logistic unit unless the evidence strongly supports that.
- model_entity_id: unique string (e.g. E1, E2). confidence: 0 to 1.
- Bbox: if you provide position_label_bbox or product_label_bbox, use NORMALIZED coords only: [x1,y1,x2,y2] with floats in [0,1], x1<x2, y1<y2. Use null if region unknown.
- has_boxes: true if boxes visible on pallet or for LOOSE_BOXES.
- Inventory visual reference images, when provided, are comparative context only. They may help interpret label style, packaging conventions, or the expected visual standard, but they are NOT primary evidence and must not be treated as direct evidence for detections.
"""

# Prompt B (global_v21_b): conservative / anti-hallucination — distinct strategy vs Prompt A.
_GLOBAL_V21_B: Final[str] = """\
Analyze the provided warehouse aisle evidence (photos and/or extracted frames). Detect logistic entities only when each unit is **unambiguously** visible as a separate physical unit.

Entity types (same taxonomy as Prompt A):
- PALLET, EMPTY_PALLET, LOOSE_BOXES (definitions unchanged).

Conservative rules (NON-NEGOTIABLE):
- Prefer **abstention** over guessing: if label text, layer count, or bbox extent is not clearly readable, use **null** for that field. Do not invent SKUs, quantities, or bboxes.
- Do **not** merge adjacent boxed units unless a clear seam, gap, or distinct label proves separation. When in doubt, emit **separate entities** with **lower confidence** rather than one merged entity.
- If occlusion, motion blur, or missing angles prevents a deterministic count or identity, set an explicit overall decision of **INSUFFICIENT_EVIDENCE** in your reasoning field and keep per-field nulls rather than extrapolating.
- **Bbox discipline**: only output position_label_bbox / product_label_bbox when the region is clearly visible; use NORMALIZED [x1,y1,x2,y2] in [0,1] or null.
- **Quantity**: never return quantity 0 for a visible unit unless the evidence clearly supports emptiness; if uncertain, prefer null + low confidence rather than a numeric guess.
- model_entity_id: unique string (E1, E2, …). confidence: 0 to 1 — use **≤0.5** when evidence is partial.
- Inventory visual references are **context only**, not primary evidence (same as Prompt A).

This profile prioritizes traceability and null-handling over aggressive extraction.
"""

# OpenAI-tuned variant for global_v21 (GPT tends to over-abstain with Gemini-oriented text).
_GLOBAL_V21_OPENAI: Final[str] = """\
Analyze the provided warehouse aisle images and detect all distinct logistic entities.

Entity types:
- PALLET: pallet structure, may contain boxes
- EMPTY_PALLET: pallet with no boxes
- LOOSE_BOXES: grouped boxes without pallet

Rules:
- One entity per physical unit. Do not merge different pallets.
- Do not invent values, but provide your best estimate when partial evidence exists.
- If a field is unclear, prefer a reasonable estimate with lower confidence instead of null.

Important:
- NEVER return quantity = 0 unless you are certain there are zero items.
- If uncertain about quantity, return null and reduce confidence.
- If an entity is visible, it must be returned.

Confidence:
- Use 0.9–1.0 when clear
- Use 0.5–0.8 when partially visible
- Use <0.5 only when uncertain

Bounding boxes:
- Use normalized coordinates [x1,y1,x2,y2]
- If unsure → null

Output:
Return valid JSON only:
{
  "total_entities_detected": number,
  "entities": [...]
}
"""

# OpenAI-tuned variant for global_v21_b: same conservative taxonomy, softer abstention for GPT.
_GLOBAL_V21_B_OPENAI: Final[str] = """\
Analyze the provided warehouse aisle evidence (photos and/or extracted frames). Detect logistic entities using the same taxonomy as Prompt B, with guidance suited to models that over-abstain under strict null-only rules.

Entity types:
- PALLET, EMPTY_PALLET, LOOSE_BOXES (definitions unchanged from Prompt A/B).

Rules:
- One entity per physical unit. Do not merge different pallets.
- Do not invent SKU text or barcodes you cannot read; use null for illegible label fields.
- For counts and similar numeric fields: when evidence is partial, prefer your best estimate with lower confidence rather than null unless the value would be a pure guess.
- If occlusion, blur, or missing angles make a count unknowable, use null for quantity, confidence ≤0.5, and you may note INSUFFICIENT_EVIDENCE in reasoning.
- Never return quantity = 0 unless you are certain there are zero items.
- model_entity_id: unique string (E1, E2, …). Bbox: normalized [x1,y1,x2,y2] in [0,1] or null.
- Inventory visual references are context only, not primary evidence.

Output:
Return valid JSON matching the required entity schema (total_entities_detected + entities array).
"""

_SYSTEM_PALLET_COUNT: Final[str] = """\
You are an expert in computer vision for logistics inventory management.
Your task is to analyze warehouse images, identify distinct pallets, and count boxes per product.

CRITICAL COUNTING LOGIC (Use the 'r' field to write this out step-by-step):
1. GRID MAPPING: Look at all available angles. Determine the Base Footprint (Width x Depth). 
   *VISUAL TIP*: Do not rely on overall shape. Look for vertical and horizontal gaps (seams) between boxes. If you see multiple labels or handles, each one belongs to a DIFFERENT box.
2. HEIGHT: Count total layers from bottom to top.
3. THEORETICAL MAX: Multiply Base x Layers (Format: "Base [w]x[d]=[layer_tot]. [n] layers=[total]").
4. DEDUCTION: Scan the TOP layer and corners across ALL frames. Are there missing boxes or empty spaces?
5. FINAL MATH: Subtract gaps from max (Format: "[total] - [missing] = [final]").

Rules:
- BOX SEPARATION: Boxes often blend together. Look for tape lines, cardboard seams, and repeated "FRAGIL" logos to distinguish individual units.
- NEVER assume a solid block. Check for hollow centers or missing top boxes.
- CROSS-REFERENCE: Use the video sequence to see the pallet from different perspectives. Merge observations.
- Assign confidence (0.0 to 1.0).
"""

_USER_PALLET_COUNT: Final[str] = """\
Analyze the attached image(s). Identify all visible distinct pallets, distinguish the products and calculate the total number of boxes conservatively.
"""

_USER_MULTI_VIEW_REDUNDANCY: Final[str] = """\
REDUNDANCY AND VIEW SELECTION (Sprint A):
- Some images may be repeated or highly similar (same angle, same framing, same visual pattern). If you detect that two or more views are redundant, IGNORE the duplicates and base your analysis on the single best view among them.
- PRIORITIZE the most useful view: sharpest (least blur), most complete (least occlusion), and with the clearest view of labels/boxes.
- Use multiple views ONLY when they add genuinely different evidence (e.g. different angle revealing hidden layers). Do NOT assume "more images = sum counts"; maintain anti-double-counting and rely on real diversity.
"""

_USER_MULTI_FRAME: Final[str] = """\
Analyze the attached sequence of images. 
CRITICAL: These images may show multiple angles of the SAME pallet, AND/OR entirely DIFFERENT pallets.

Your specific tasks:
- Carefully cross-reference visual clues (background racks, labels, shrink wrap patterns, stacking geometry) to determine distinct pallets.
- MERGE observations of the same pallet across different frames into a single consolidated entry.
- Separate distinct pallets into individual entries.
- Ensure absolutely no double-counting occurs. Provide the final, most accurate count for each distinct pallet based on all combined views.

REDUNDANCY (Sprint A): There may be repeated or very similar images (same angle/framing). If two or more views are redundant, ignore the duplicates and use only the best one (sharpest, most complete, least occlusion). Use multiple views only when they add genuinely different evidence; do not assume "more images = sum".
"""

_USER_MULTI_VIEW_ANTI_SUM: Final[str] = """\
The attached images are multiple views of the SAME pallet (one physical pallet).
Your task: MERGE evidence across views into ONE consolidated count.

NON-NEGOTIABLE:
1) Do NOT sum counts across images. Use views only to reveal hidden faces/layers.
2) Use a grid method:
   - Estimate Base Footprint = width x depth (count seams/gaps between boxes).
   - Estimate Height = number of layers.
   - Total theoretical max = (w x d) x layers.
   - Subtract missing boxes/voids if clearly visible.
3) Depth is critical: use side/angled views to infer depth layers. Do not return a low number just because only the front face is visible.

If depth/layers cannot be inferred deterministically from the provided views (occlusion, blur, missing angles):
- return decision = "INSUFFICIENT_EVIDENCE" and provide the best bounded estimate range in r (e.g., min/max), with low confidence.

Output:
- Return ONLY one pallet entry (single JSON) that matches the provided schema.
- Put step-by-step reasoning in the 'r' field (short and structured).
- Return confidence as a numeric value (0.0 to 1.0).
"""

# ----------------------------
# Diccionario unificado de prompts
# Valores: str = híbrido legacy | dict default/openai = híbrido multi-proveedor | system/user = legacy
# ----------------------------

PROMPTS: Dict[str, Union[str, Dict[str, str]]] = {
    # Híbrido (una llamada por video; HYBRID_PROMPT) — ``default`` = Gemini y demás; ``openai`` = GPT
    "global_v21": {"default": _GLOBAL_V21, "openai": _GLOBAL_V21_OPENAI},
    # Prompt B — conservative; OpenAI variant mitigates over-abstention
    "global_v21_b": {"default": _GLOBAL_V21_B, "openai": _GLOBAL_V21_B_OPENAI},
    # Legacy (system + user; no usados por el flujo híbrido único)
    "pallet_count_simple": {"system": _SYSTEM_PALLET_COUNT, "user": _USER_PALLET_COUNT},
    "multi_frame_consolidated": {"system": _SYSTEM_PALLET_COUNT, "user": _USER_MULTI_FRAME},
    "multi_view_per_track": {
        "system": _SYSTEM_PALLET_COUNT,
        "user": _USER_MULTI_VIEW_ANTI_SUM + "\n\n" + _USER_MULTI_VIEW_REDUNDANCY,
    },
}

# Compatibilidad: nombres usados en tests y documentación
GLOBAL_ENTITY_ANALYSIS_PROMPT_V21: Final[str] = _GLOBAL_V21


def _hybrid_default_text(entry: Union[str, Dict[str, str]]) -> Optional[str]:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("default"), str):
        return entry["default"]
    return None


HYBRID_PROMPTS: Dict[str, str] = {
    k: dv for k, v in PROMPTS.items() if (dv := _hybrid_default_text(v)) is not None
}


def registered_hybrid_prompt_keys() -> frozenset[str]:
    """Keys accepted for per-job hybrid prompt selection (API / processing)."""
    return frozenset(HYBRID_PROMPTS.keys())


def _global_v21_default_text() -> str:
    g = PROMPTS["global_v21"]
    assert isinstance(g, dict)
    return str(g["default"]).rstrip()


def _resolve_hybrid_for_provider(entry: Union[str, Dict[str, str]], provider_key: Optional[str]) -> str:
    """Pick provider-specific hybrid text when present; otherwise ``default`` or legacy fallback."""
    pk = (provider_key or "").strip().lower()
    if isinstance(entry, str):
        return entry.rstrip()
    if isinstance(entry, dict):
        if "system" in entry:
            return _global_v21_default_text()
        if isinstance(entry.get("default"), str):
            if pk == "openai" and isinstance(entry.get("openai"), str):
                return str(entry["openai"]).rstrip()
            return str(entry["default"]).rstrip()
    return _global_v21_default_text()


def get_hybrid_prompt(
    profile_name: str = "global_v21",
    provider_key: Optional[str] = None,
) -> str:
    """Return the base analysis prompt for the hybrid pipeline (no Epic D enrichment).

    Profile is selected via HYBRID_PROMPT env. Entries with ``default`` / ``openai``
    resolve by ``provider_key`` (e.g. ``openai`` uses the OpenAI-tuned variant when defined).
    Unknown profile or non-hybrid dict entries fall back to ``global_v21`` default text.

    Does not append product/label association. Call enrich_prompt_with_product_label_association
    at the request-building layer where Epic D behavior is intended.

    Args:
        profile_name: Profile name (e.g. global_v21).
        provider_key: Pipeline provider (e.g. ``openai``, ``gemini``). None uses default variant.

    Returns:
        Base prompt text only.
    """
    raw = PROMPTS.get(profile_name)
    if raw is None:
        return _resolve_hybrid_for_provider(PROMPTS["global_v21"], provider_key)
    return _resolve_hybrid_for_provider(raw, provider_key)


def enrich_prompt_with_product_label_association(base_prompt: str) -> str:
    """Append Epic 3.1.D product/label association instructions to the base prompt.

    Call this explicitly at the request-building layer (e.g. pipeline adapter) where
    Epic D behavior is intended. Do not modify get_hybrid_prompt to append this globally.

    Clarifies: internal_code = product/SKU from product label; position_barcode =
    position/pallet barcode. Provider should not mix them.

    Args:
        base_prompt: Base analysis prompt (e.g. from get_hybrid_prompt()).

    Returns:
        base_prompt + product/label association block.
    """
    return base_prompt.rstrip() + _PRODUCT_LABEL_ASSOCIATION


# Epic 3.1.A — Enrich prompt with image identity for traceability (provider receives image IDs)
_TRACEABILITY_INSTRUCTION: Final[str] = """

TRACEABILITY (v3.1): Each input image has a unique identifier below. For every entity or counted result you return, you MUST include the exact source_image_id of the image used as evidence for that result. Do not invent IDs. Only use image IDs from the list below.
"""

# Epic 3.1.D — Product/label association: clarify internal_code vs position_barcode
_PRODUCT_LABEL_ASSOCIATION: Final[str] = """

PRODUCT AND LABEL ASSOCIATION (v3.1.D): For each entity, use internal_code ONLY for the product/SKU code from the product label (the label on the boxes or product). Use position_barcode ONLY for the position or pallet barcode/label (location or pallet identifier). Do not mix them: internal_code = product identifier, position_barcode = position/pallet identifier.
"""


def enrich_prompt_with_image_ids(
    base_prompt: str,
    images: List[JobImage],
) -> str:
    """Append image list and traceability instruction to the base prompt (Epic 3.1.A).

    The provider receives explicit image identifiers so it can return source_image_id
    per result in a future epic. No response parsing in Epic A.

    Args:
        base_prompt: Existing analysis prompt text.
        images: List of JobImage (order must match frame order). upload_order is 1-based.

    Returns:
        base_prompt + image list block + traceability instruction.
    """
    if not images:
        return base_prompt
    lines = ["\n\nInput images (use these exact IDs as source_image_id per result):"]
    for img in images:
        lines.append(
            f"- {img.image_id} (upload_order={img.upload_order}, original_filename={img.original_filename!r})"
        )
    block = "\n".join(lines)
    return base_prompt.rstrip() + "\n" + block + _TRACEABILITY_INSTRUCTION
