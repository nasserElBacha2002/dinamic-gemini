"""Spatial relation scoring between OCR label anchors and value candidates."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.client_supplier.extraction_profile import SpatialRelation


@dataclass(frozen=True)
class BoundingBox:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def cx(self) -> float:
        return self.left + self.width / 2.0

    @property
    def cy(self) -> float:
        return self.top + self.height / 2.0


@dataclass(frozen=True)
class SpatialRelationResult:
    relation: str
    normalized_distance: float
    matches_allowed: bool


class OcrSpatialRelationEvaluator:
    """Compute BELOW / RIGHT_OF / SAME_ROW / SAME_COLUMN / NEAR from bounding boxes."""

    def __init__(self, *, image_diagonal: float | None = None) -> None:
        self._diag = float(image_diagonal) if image_diagonal and image_diagonal > 0 else None

    def evaluate(
        self,
        *,
        anchor: BoundingBox,
        value: BoundingBox,
        allowed: tuple[str, ...] | list[str],
        maximum_anchor_distance_ratio: float | None = None,
    ) -> SpatialRelationResult:
        relation = self.infer_relation(anchor, value)
        dist = self.normalized_distance(anchor, value)
        allowed_set = {str(a).strip().upper() for a in allowed if str(a).strip()}
        matches = (not allowed_set) or (relation in allowed_set) or (
            SpatialRelation.NEAR.value in allowed_set and relation == SpatialRelation.NEAR.value
        )
        if maximum_anchor_distance_ratio is not None and dist > float(
            maximum_anchor_distance_ratio
        ):
            matches = False
        return SpatialRelationResult(
            relation=relation,
            normalized_distance=dist,
            matches_allowed=matches,
        )

    def infer_relation(self, anchor: BoundingBox, value: BoundingBox) -> str:
        # Vertical below with horizontal overlap → BELOW
        horiz_overlap = min(anchor.right, value.right) - max(anchor.left, value.left)
        vert_overlap = min(anchor.bottom, value.bottom) - max(anchor.top, value.top)
        same_row = vert_overlap > 0 and abs(anchor.cy - value.cy) <= max(
            anchor.height, value.height
        ) * 0.6
        same_col = horiz_overlap > 0 and abs(anchor.cx - value.cx) <= max(
            anchor.width, value.width
        ) * 0.75
        if value.top >= anchor.bottom - 2 and same_col:
            return SpatialRelation.BELOW.value
        if value.left >= anchor.right - 2 and same_row:
            return SpatialRelation.RIGHT_OF.value
        if same_row and same_col:
            return SpatialRelation.SAME_CELL.value
        if same_row:
            return SpatialRelation.SAME_ROW.value
        if same_col:
            return SpatialRelation.SAME_COLUMN.value
        return SpatialRelation.NEAR.value

    def normalized_distance(self, a: BoundingBox, b: BoundingBox) -> float:
        dx = a.cx - b.cx
        dy = a.cy - b.cy
        dist = (dx * dx + dy * dy) ** 0.5
        diag = self._diag
        if diag is None or diag <= 0:
            # Fallback: normalize by average box size.
            scale = max(1.0, (a.width + a.height + b.width + b.height) / 4.0)
            return float(dist / scale)
        return float(dist / diag)


__all__ = [
    "BoundingBox",
    "OcrSpatialRelationEvaluator",
    "SpatialRelationResult",
]
