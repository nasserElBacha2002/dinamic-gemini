"""
Módulo unificado de prompts para Gemini API.

Todos los prompts viven en el diccionario PROMPTS. El pipeline híbrido usa
get_hybrid_prompt() con la variable de entorno HYBRID_PROMPT (default: global_v21).
Valores del diccionario: str (prompt único) o dict con "system"/"user" (legacy).
"""

from typing import Dict, Final, List, Union

from src.jobs.image_identity import JobImage

# Textos base (referenciados por PROMPTS)
_GLOBAL_V21: Final[str] = """\
Analyze the frames from a warehouse aisle video. Detect all distinct logistic entities (one per entity).

Entity types:
- PALLET: pallet structure, may have boxes and position/product labels.
- EMPTY_PALLET: pallet structure with no boxes on top.
- LOOSE_BOXES: grouped boxes without pallet (do NOT count as pallet).

Rules:
- One entity per detection. Do NOT duplicate or merge. Do NOT infer hidden entities.
- Do not invent values. Use null if not clearly readable.
- model_entity_id: unique string (e.g. E1, E2). confidence: 0 to 1.
- Bbox: if you provide position_label_bbox or product_label_bbox, use NORMALIZED coords only: [x1,y1,x2,y2] with floats in [0,1], x1<x2, y1<y2. Use null if region unknown.
- has_boxes: true if boxes visible on pallet or for LOOSE_BOXES.
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
# Valores: str = prompt único (híbrido) | dict con "system"/"user" = legacy
# ----------------------------

PROMPTS: Dict[str, Union[str, Dict[str, str]]] = {
    # Híbrido (una llamada por video; HYBRID_PROMPT)
    "global_v21": _GLOBAL_V21,
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
HYBRID_PROMPTS: Dict[str, str] = {k: v for k, v in PROMPTS.items() if isinstance(v, str)}


def get_hybrid_prompt(profile_name: str = "global_v21") -> str:
    """Devuelve el prompt de análisis global para el pipeline híbrido.

    El perfil se elige con la variable de entorno HYBRID_PROMPT. Solo perfiles
    con valor str en PROMPTS son válidos para híbrido; si no existe o es legacy, se usa global_v21.

    Args:
        profile_name: Nombre del perfil (ej. global_v21).

    Returns:
        Texto del prompt.
    """
    raw = PROMPTS.get(profile_name, PROMPTS["global_v21"])
    return raw if isinstance(raw, str) else PROMPTS["global_v21"]


# Epic 3.1.A — Enrich prompt with image identity for traceability (provider receives image IDs)
_TRACEABILITY_INSTRUCTION: Final[str] = """

TRACEABILITY (v3.1): Each input image has a unique identifier below. For every entity or counted result you return, you MUST include the exact source_image_id of the image used as evidence for that result. Do not invent IDs. Only use image IDs from the list below.
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
