"""
Prompt para análisis global de pallets (v2.0 hybrid — una llamada por video).

Stage 3: hardened contract, explicit schema, strict JSON-only.
"""

from typing import Final

GLOBAL_PALLET_ANALYSIS_PROMPT: Final[str] = """\
You are analyzing multiple representative frames from a warehouse aisle video.
The drone passes each pallet only once.

Task: detect all distinct pallets visible across the frames.

Rules:
- Each pallet must appear only once. Do NOT duplicate or merge pallets.
- Do NOT infer hidden pallets. Report only pallets you actually see.
- If uncertain, lower confidence instead of guessing. Do not invent values.
- If a value cannot be clearly read, use null.
- Return ONLY valid JSON. No explanations, no markdown, no comments, no extra text, no trailing commas.

Schema (types are strict):

{
  "total_pallets_detected": <integer, count of pallets in list>,
  "pallets": [
    {
      "pallet_id": <string, e.g. "P1">,
      "has_label": <boolean>,
      "internal_code": <string or null>,
      "quantity": <integer or null>,
      "estimated_visible_boxes": <integer or null>,
      "confidence": <float in [0, 1]>
    }
  ]
}

Example (structure only):

{"total_pallets_detected": 2, "pallets": [{"pallet_id": "P1", "has_label": true, "internal_code": "10145317", "quantity": 15, "estimated_visible_boxes": null, "confidence": 0.94}, {"pallet_id": "P2", "has_label": false, "internal_code": null, "quantity": null, "estimated_visible_boxes": 12, "confidence": 0.78}]}

Per pallet:
- If a logistics label is visible: set has_label true, extract internal_code and quantity when readable.
- If no label is visible: set has_label false, set estimated_visible_boxes when possible.
- confidence must be between 0 and 1.
"""
