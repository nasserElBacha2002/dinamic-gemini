"""
Prompt para análisis global (hybrid v2.1 — una llamada por video, Structured Output).
"""

from typing import Final

GLOBAL_ENTITY_ANALYSIS_PROMPT_V21: Final[str] = """\
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
