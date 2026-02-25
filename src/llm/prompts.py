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

USER_PROMPT_MULTI_FRAME: Final[str] = """\
Analyze the attached sequence of images. 
CRITICAL: These images may show multiple angles of the SAME pallet, AND/OR entirely DIFFERENT pallets.

Your specific tasks:
- Carefully cross-reference visual clues (background racks, labels, shrink wrap patterns, stacking geometry) to determine distinct pallets.
- MERGE observations of the same pallet across different frames into a single consolidated entry.
- Separate distinct pallets into individual entries.
- Ensure absolutely no double-counting occurs. Provide the final, most accurate count for each distinct pallet based on all combined views.
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
}

def get_prompt_profile(profile_name: str = "pallet_count_simple") -> Dict[str, str]:
    if profile_name not in PROMPT_PROFILES:
        available = ", ".join(PROMPT_PROFILES.keys())
        raise ValueError(
            f"Perfil de prompt '{profile_name}' no encontrado. "
            f"Perfiles disponibles: {available}"
        )
    return PROMPT_PROFILES[profile_name].copy()