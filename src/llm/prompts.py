"""
Módulo de prompts para Gemini API.
Define los prompts del sistema y usuario para diferentes perfiles de análisis.
"""

from typing import Dict, Final

# ----------------------------
# Prompt Profile: Pallet Counting (Single & Multi-frame)
# ----------------------------

SYSTEM_PROMPT_PALLET_COUNT: Final[str] = """\
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

USER_PROMPT_PALLET_COUNT: Final[str] = """\
Analyze the attached image(s). Identify all visible distinct pallets, distinguish the products and calculate the total number of boxes conservatively.
"""

# Bloque Sprint A: manejo de redundancia (imágenes repetidas o muy similares)
USER_PROMPT_MULTI_VIEW_REDUNDANCY: Final[str] = """\
REDUNDANCY AND VIEW SELECTION (Sprint A):
- Some images may be repeated or highly similar (same angle, same framing, same visual pattern). If you detect that two or more views are redundant, IGNORE the duplicates and base your analysis on the single best view among them.
- PRIORITIZE the most useful view: sharpest (least blur), most complete (least occlusion), and with the clearest view of labels/boxes.
- Use multiple views ONLY when they add genuinely different evidence (e.g. different angle revealing hidden layers). Do NOT assume "more images = sum counts"; maintain anti-double-counting and rely on real diversity.
"""

USER_PROMPT_MULTI_FRAME: Final[str] = """\
Analyze the attached sequence of images. 
CRITICAL: These images may show multiple angles of the SAME pallet, AND/OR entirely DIFFERENT pallets.

Your specific tasks:
- Carefully cross-reference visual clues (background racks, labels, shrink wrap patterns, stacking geometry) to determine distinct pallets.
- MERGE observations of the same pallet across different frames into a single consolidated entry.
- Separate distinct pallets into individual entries.
- Ensure absolutely no double-counting occurs. Provide the final, most accurate count for each distinct pallet based on all combined views.

REDUNDANCY (Sprint A): There may be repeated or very similar images (same angle/framing). If two or more views are redundant, ignore the duplicates and use only the best one (sharpest, most complete, least occlusion). Use multiple views only when they add genuinely different evidence; do not assume "more images = sum".
"""

# Sprint A: 1 request por track (vistas del MISMO pallet)
USER_PROMPT_MULTI_VIEW_ANTI_SUM: Final[str] = """\
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
# Perfiles de prompt
# ----------------------------

PROMPT_PROFILES: Dict[str, Dict[str, str]] = {
    "pallet_count_simple": {
        "system": SYSTEM_PROMPT_PALLET_COUNT,
        "user": USER_PROMPT_PALLET_COUNT,
    },
    "multi_frame_consolidated": {
        "system": SYSTEM_PROMPT_PALLET_COUNT,
        "user": USER_PROMPT_MULTI_FRAME,
    },
    "multi_view_per_track": {
        "system": SYSTEM_PROMPT_PALLET_COUNT,
        "user": USER_PROMPT_MULTI_VIEW_ANTI_SUM + "\n\n" + USER_PROMPT_MULTI_VIEW_REDUNDANCY,
    },
}

def get_prompt_profile(profile_name: str = "pallet_count_simple") -> Dict[str, str]:
    if profile_name not in PROMPT_PROFILES:
        available = ", ".join(PROMPT_PROFILES.keys())
        raise ValueError(
            f"Perfil de prompt '{profile_name}' no encontrado. "
            f"Perfiles disponibles: {available}"
        )
    return PROMPT_PROFILES[profile_name].copy()