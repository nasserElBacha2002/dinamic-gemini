"""Phase 6 — resolve reference-template annotation hints for INTERNAL_OCR.

Hints boost spatial / anchor search; they never hard-crop the OCR region.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from src.application.ports.supplier_extraction_profile_repository import (
    SupplierReferenceAnnotationRepository,
)
from src.domain.client_supplier.extraction_profile import (
    ReferenceAnnotation,
    SpatialRelation,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReferenceTemplateHint:
    field_key: str
    anchor_texts: tuple[str, ...]
    spatial_relation: SpatialRelation
    normalized_polygon: tuple[tuple[float, float], ...] | None
    priority: int
    max_distance_ratio: float | None
    profile_id: str | None
    template_image_id: str
    required: bool = False


@dataclass
class ReferenceTemplateHintResolution:
    hints: list[ReferenceTemplateHint] = field(default_factory=list)
    annotation_used: list[str] = field(default_factory=list)
    annotation_missed: list[str] = field(default_factory=list)
    profile_id: str | None = None
    template_image_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


class ReferenceTemplateHintResolver:
    """Load annotations for a template image and expose OCR boost hints."""

    def __init__(
        self,
        annotation_repo: SupplierReferenceAnnotationRepository | None = None,
    ) -> None:
        self._annotation_repo = annotation_repo

    def resolve(
        self,
        *,
        template_image_id: str | None,
        profile_id: str | None = None,
        annotations: Sequence[ReferenceAnnotation] | None = None,
    ) -> ReferenceTemplateHintResolution:
        if annotations is None:
            if not template_image_id or self._annotation_repo is None:
                return ReferenceTemplateHintResolution(
                    evidence={"annotation_hints": "unavailable"}
                )
            annotations = list(self._annotation_repo.list_by_template(template_image_id))

        hints: list[ReferenceTemplateHint] = []
        for ann in sorted(annotations, key=lambda a: (a.priority, a.id)):
            if profile_id and ann.profile_id and ann.profile_id != profile_id:
                continue
            hints.append(
                ReferenceTemplateHint(
                    field_key=ann.field_key,
                    anchor_texts=tuple(ann.anchor_texts),
                    spatial_relation=ann.spatial_relation,
                    normalized_polygon=ann.normalized_polygon,
                    priority=ann.priority,
                    max_distance_ratio=ann.max_distance_ratio,
                    profile_id=ann.profile_id,
                    template_image_id=ann.template_image_id,
                    required=ann.required,
                )
            )

        evidence = {
            "annotation_hint_count": len(hints),
            "template_image_id": template_image_id,
            "profile_id": profile_id,
            "anchors": [list(h.anchor_texts) for h in hints],
            "relations": [h.spatial_relation.value for h in hints],
        }
        logger.info(
            "reference_template.hints_resolved template=%s profile=%s count=%s",
            template_image_id,
            profile_id,
            len(hints),
        )
        return ReferenceTemplateHintResolution(
            hints=hints,
            profile_id=profile_id,
            template_image_id=template_image_id,
            evidence=evidence,
        )

    def record_hit(
        self, resolution: ReferenceTemplateHintResolution, field_key: str
    ) -> None:
        resolution.annotation_used.append(field_key)
        resolution.evidence["annotation_used"] = list(resolution.annotation_used)

    def record_miss(
        self, resolution: ReferenceTemplateHintResolution, field_key: str
    ) -> None:
        resolution.annotation_missed.append(field_key)
        resolution.evidence["annotation_missed"] = list(resolution.annotation_missed)


__all__ = [
    "ReferenceTemplateHint",
    "ReferenceTemplateHintResolution",
    "ReferenceTemplateHintResolver",
]
