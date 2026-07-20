"""Label region detection for INTERNAL_OCR (Phase 4 corrections).

Locates an inventory label inside a full pallet photo using contour geometry
and optional light OCR anchor matching. Coordinates are normalized [0,1].
"""

from __future__ import annotations

import io
import logging
import time
import unicodedata
from dataclasses import dataclass

from src.domain.client_supplier.extraction_profile import (
    AnchorMatchPolicy,
    LabelBackgroundHint,
    LabelDetectionRules,
    LabelOrientationHint,
    LabelShapeHint,
)

logger = logging.getLogger(__name__)

NormalizedPolygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class LabelRegionCandidate:
    polygon: NormalizedPolygon
    relative_area: float
    rectangularity_score: float | None
    brightness_score: float | None
    matched_anchors: tuple[str, ...]
    anchor_score: float
    total_score: float
    bbox_px: tuple[int, int, int, int] | None = None  # x, y, w, h


@dataclass(frozen=True)
class LabelDetectionResult:
    detected: bool
    candidates: tuple[LabelRegionCandidate, ...]
    selected_candidate: LabelRegionCandidate | None
    failure_reason: str | None
    duration_ms: int
    used_full_image_fallback: bool = False
    light_ocr_executed: bool = False
    light_ocr_failed: bool = False
    anchor_requirement_met: bool | None = None
    anchor_match_policy: str | None = None


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).casefold().strip()


class LabelRegionDetector:
    """Detect approximately rectangular label regions; score with anchors when available."""

    def __init__(
        self,
        *,
        rules: LabelDetectionRules | None = None,
        light_ocr_reader: object | None = None,
        light_ocr_language: str = "spa+eng",
        light_ocr_timeout_seconds: float = 3.0,
        max_light_ocr_candidates: int = 3,
    ) -> None:
        self._rules = rules or LabelDetectionRules()
        self._light_ocr_reader = light_ocr_reader
        self._light_ocr_language = light_ocr_language
        self._light_ocr_timeout_seconds = light_ocr_timeout_seconds
        self._max_light_ocr_candidates = max_light_ocr_candidates

    def detect(self, image_bytes: bytes) -> LabelDetectionResult:
        started = time.monotonic()
        rules = self._rules
        if not rules.enabled:
            return LabelDetectionResult(
                detected=False,
                candidates=(),
                selected_candidate=None,
                failure_reason="LABEL_DETECTION_DISABLED",
                duration_ms=int((time.monotonic() - started) * 1000),
                used_full_image_fallback=rules.allow_full_image_fallback,
            )

        try:
            rgb, width, height = self._decode_rgb(image_bytes)
        except (OSError, ValueError) as exc:
            return LabelDetectionResult(
                detected=False,
                candidates=(),
                selected_candidate=None,
                failure_reason=f"OCR_IMAGE_INVALID:{exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        try:
            geometric = self._geometric_candidates(rgb, width, height)
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            logger.warning("label_detection.geometry_failed err=%s", exc)
            geometric = []

        scored: list[LabelRegionCandidate] = []
        light_ocr_executed = False
        light_ocr_failed = False
        for cand in geometric[: max(1, int(rules.maximum_candidate_regions))]:
            matched: tuple[str, ...] = ()
            anchor_score = 0.0
            if self._light_ocr_reader is not None and len(scored) < self._max_light_ocr_candidates:
                matched, anchor_score, ocr_ok = self._score_anchors(rgb, cand)
                if ocr_ok:
                    light_ocr_executed = True
                else:
                    light_ocr_failed = True
            orient_bonus = self._orientation_bonus(cand, rules.expected_orientation)
            total = (
                0.30 * (cand.rectangularity_score or 0.0)
                + 0.20 * (cand.brightness_score or 0.0)
                + 0.40 * anchor_score
                + 0.10 * orient_bonus
            )
            area_bonus = 0.0
            if 0.01 <= cand.relative_area <= 0.25:
                area_bonus = 0.1
            scored.append(
                LabelRegionCandidate(
                    polygon=cand.polygon,
                    relative_area=cand.relative_area,
                    rectangularity_score=cand.rectangularity_score,
                    brightness_score=cand.brightness_score,
                    matched_anchors=matched,
                    anchor_score=anchor_score,
                    total_score=total + area_bonus,
                    bbox_px=cand.bbox_px,
                )
            )

        scored.sort(key=lambda c: c.total_score, reverse=True)
        policy = self._resolve_policy(rules)
        min_anchors = max(0, int(rules.minimum_anchor_matches))
        selected: LabelRegionCandidate | None = None
        failure: str | None = None
        anchor_requirement_met: bool | None = None

        eligible = list(scored)
        if policy is AnchorMatchPolicy.ANCHORS_REQUIRED and min_anchors > 0:
            if light_ocr_executed and not light_ocr_failed:
                eligible = [
                    c for c in scored if len(c.matched_anchors) >= min_anchors
                ]
                anchor_requirement_met = bool(eligible)
                if not eligible:
                    failure = "LABEL_ANCHORS_INSUFFICIENT"
            elif light_ocr_failed:
                # Light OCR failed: cannot enforce anchors → do not pick by geometry alone.
                eligible = []
                anchor_requirement_met = False
                failure = "LABEL_LIGHT_OCR_FAILED"
            else:
                # Light OCR not available: cannot require anchors.
                eligible = []
                anchor_requirement_met = False
                failure = "LABEL_ANCHORS_REQUIRED_BUT_LIGHT_OCR_UNAVAILABLE"
        elif policy is AnchorMatchPolicy.ANCHORS_PREFERRED and min_anchors > 0:
            preferred = [c for c in scored if len(c.matched_anchors) >= min_anchors]
            if preferred:
                eligible = preferred
                anchor_requirement_met = True
            else:
                anchor_requirement_met = False if light_ocr_executed else None
        else:
            # GEOMETRY_ONLY_ALLOWED
            anchor_requirement_met = None

        if eligible:
            selected = eligible[0]
            failure = None
        elif failure is None:
            failure = "LABEL_NOT_DETECTED"

        detected = selected is not None
        used_fallback = False
        if not detected and rules.allow_full_image_fallback:
            used_fallback = True
            failure = failure or "LABEL_NOT_DETECTED"

        return LabelDetectionResult(
            detected=detected,
            candidates=tuple(scored[: rules.maximum_candidate_regions]),
            selected_candidate=selected,
            failure_reason=None if detected else failure,
            duration_ms=int((time.monotonic() - started) * 1000),
            used_full_image_fallback=used_fallback,
            light_ocr_executed=light_ocr_executed,
            light_ocr_failed=light_ocr_failed,
            anchor_requirement_met=anchor_requirement_met,
            anchor_match_policy=policy.value,
        )

    def _resolve_policy(self, rules: LabelDetectionRules) -> AnchorMatchPolicy:
        if rules.anchor_match_policy is not None:
            return rules.anchor_match_policy
        if int(rules.minimum_anchor_matches or 0) > 0:
            return AnchorMatchPolicy.ANCHORS_REQUIRED
        return AnchorMatchPolicy.GEOMETRY_ONLY_ALLOWED

    def _orientation_bonus(
        self, cand: LabelRegionCandidate, expected: LabelOrientationHint
    ) -> float:
        if cand.bbox_px is None or expected is LabelOrientationHint.ANY:
            return 0.5
        _x, _y, w, h = cand.bbox_px
        if w <= 0 or h <= 0:
            return 0.0
        ratio = w / float(h)
        if expected is LabelOrientationHint.HORIZONTAL:
            return 1.0 if ratio >= 1.15 else 0.2
        if expected is LabelOrientationHint.VERTICAL:
            return 1.0 if ratio <= 0.85 else 0.2
        if expected is LabelOrientationHint.SQUARE_OR_VERTICAL:
            return 1.0 if ratio <= 1.15 else 0.3
        return 0.5

    def _decode_rgb(self, content: bytes):
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(content)) as img:
            oriented = ImageOps.exif_transpose(img) or img
            rgb = oriented.convert("RGB")
            w, h = rgb.size
            if w < 8 or h < 8:
                raise ValueError("image too small")
            # Decompression bomb guard — Pillow may already raise; enforce soft cap.
            if w * h > 40_000_000:
                raise ValueError("image dimensions exceed safe limit")
            return rgb, int(w), int(h)

    def _geometric_candidates(self, rgb, width: int, height: int) -> list[LabelRegionCandidate]:
        import cv2
        import numpy as np

        arr = np.asarray(rgb)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        rules = self._rules

        binaries: list = []
        if rules.expected_background is LabelBackgroundHint.LIGHT:
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if float(np.mean(otsu)) < 127:
                otsu = cv2.bitwise_not(otsu)
            binaries.append(otsu)
            # Bright-pass: keep only high-luminance paper-like regions.
            _, bright = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            binaries.append(bright)
        elif rules.expected_background is LabelBackgroundHint.DARK:
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            binaries.append(otsu)
        else:
            edges = cv2.Canny(gray, 50, 150)
            binaries.append(cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1))

        image_area = float(width * height)
        out: list[LabelRegionCandidate] = []
        seen_boxes: set[tuple[int, int, int, int]] = set()

        for binary in binaries:
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = float(cv2.contourArea(cnt))
                if area <= 0:
                    continue
                rel = area / image_area
                if rel < rules.minimum_relative_area or rel > rules.maximum_relative_area:
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                key = (x // 4, y // 4, w // 4, h // 4)
                if key in seen_boxes:
                    continue
                seen_boxes.add(key)
                if w < 20 or h < 20:
                    continue
                rect_area = float(w * h)
                rectangularity = area / rect_area if rect_area > 0 else 0.0
                if rules.expected_shape is LabelShapeHint.RECTANGULAR and rectangularity < 0.75:
                    continue
                if (
                    rules.expected_shape is LabelShapeHint.APPROXIMATELY_RECTANGULAR
                    and rectangularity < 0.55
                ):
                    continue

                roi = gray[y : y + h, x : x + w]
                brightness = float(np.mean(roi)) / 255.0 if roi.size else 0.0
                if rules.expected_background is LabelBackgroundHint.LIGHT and brightness < 0.35:
                    continue
                if rules.expected_background is LabelBackgroundHint.DARK and brightness > 0.65:
                    continue

                polygon: NormalizedPolygon = (
                    (x / width, y / height),
                    ((x + w) / width, y / height),
                    ((x + w) / width, (y + h) / height),
                    (x / width, (y + h) / height),
                )
                out.append(
                    LabelRegionCandidate(
                        polygon=polygon,
                        relative_area=rel,
                        rectangularity_score=rectangularity,
                        brightness_score=brightness,
                        matched_anchors=(),
                        anchor_score=0.0,
                        total_score=0.0,
                        bbox_px=(int(x), int(y), int(w), int(h)),
                    )
                )

        out.sort(key=lambda c: c.relative_area, reverse=True)
        return out[: max(1, int(rules.maximum_candidate_regions) * 2)]

    def _score_anchors(
        self, rgb, cand: LabelRegionCandidate
    ) -> tuple[tuple[str, ...], float, bool]:
        if cand.bbox_px is None:
            return (), 0.0, False
        x, y, w, h = cand.bbox_px
        try:
            crop = rgb.crop((x, y, x + w, y + h))
            longest = max(crop.size)
            if longest > 800:
                scale = 800 / float(longest)
                crop = crop.resize(
                    (max(1, int(crop.size[0] * scale)), max(1, int(crop.size[1] * scale)))
                )
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            from src.application.ports.internal_label_reader import (
                InternalOcrContext,
                PreparedImage,
            )

            prepared = PreparedImage(
                content=buf.getvalue(),
                width=int(crop.size[0]),
                height=int(crop.size[1]),
                variant_name="label_light_ocr",
            )
            ctx = InternalOcrContext(
                job_id="label-detect",
                asset_id="label-detect",
                client_id=None,
                language=self._light_ocr_language,
                timeout_seconds=self._light_ocr_timeout_seconds,
                max_image_dimension=800,
                page_segmentation_mode=11,
            )
            read = self._light_ocr_reader.read(prepared, ctx)  # type: ignore[union-attr]
            text = _fold(getattr(read, "full_text", "") or "")
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as exc:
            logger.debug("label_detection.light_ocr_failed err=%s", exc)
            return (), 0.0, False

        primary = list(self._rules.primary_anchors) + list(self._rules.secondary_anchors)
        matched: list[str] = []
        for anchor in primary:
            folded = _fold(anchor)
            if folded and folded in text:
                matched.append(anchor)
        if not matched:
            return (), 0.0, True
        primary_hits = sum(
            1 for a in matched if _fold(a) in {_fold(p) for p in self._rules.primary_anchors}
        )
        score = min(1.0, 0.55 * primary_hits + 0.25 * len(matched))
        return tuple(matched), score, True


__all__ = [
    "LabelDetectionResult",
    "LabelRegionCandidate",
    "LabelRegionDetector",
    "NormalizedPolygon",
]
