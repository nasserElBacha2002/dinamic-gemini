"""
Prompt para análisis global de pallets (v2.0 hybrid — una llamada por video).

Minimalista, JSON estricto. No pedir descripciones ni metadata extra.
"""

from typing import Final

GLOBAL_PALLET_ANALYSIS_PROMPT: Final[str] = """\
You are analyzing multiple representative frames extracted from a warehouse aisle video.
The drone passes each pallet only once.

Your task is to detect all distinct pallets visible across the frames.

Important constraints:
- Each pallet must appear only once.
- Do NOT duplicate pallets.
- Do NOT merge different pallets.
- Do NOT invent pallets.
- If uncertain, reduce confidence.
- If a value cannot be clearly read, return null.

For each pallet:
- Determine if a logistics label is visible.
- If a label is visible: extract the internal_code and the quantity.
- If no label is visible: estimate the number of visible boxes.

Return STRICT JSON using this exact structure:

{
  "total_pallets_detected": integer,
  "pallets": [
    {
      "pallet_id": "P1",
      "has_label": true or false,
      "internal_code": string or null,
      "quantity": integer or null,
      "estimated_visible_boxes": integer or null,
      "confidence": float between 0 and 1
    }
  ]
}

Important:
- Return ONLY valid JSON.
- No explanations. No markdown. No comments. No extra text. No trailing commas.
"""
