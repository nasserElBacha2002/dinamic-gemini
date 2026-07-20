"""OCR variant execution plan (versioned, bounded)."""

from __future__ import annotations

from dataclasses import dataclass


VARIANT_PLAN_VERSION = "v1"


@dataclass(frozen=True)
class OcrVariantSpec:
    preprocess_variant: str
    psm: int
    name: str


def build_ocr_variant_plan(
    *,
    max_total_engine_calls: int = 3,
    enable_gray_contrast: bool = True,
    enable_adaptive_threshold: bool = True,
    enable_deskew: bool = False,
    page_segmentation_modes: tuple[int, ...] = (6, 11, 12),
) -> tuple[OcrVariantSpec, ...]:
    """Prioritized (preprocess, psm) pairs — never PSM-only on original until preprocess is used.

    Example for max_total_engine_calls=3:
      original + PSM6
      adaptive_threshold + PSM6
      adaptive_threshold + PSM11
    """
    max_calls = max(1, int(max_total_engine_calls))
    psms = tuple(int(p) for p in (page_segmentation_modes or (6,)))
    primary_psm = psms[0] if psms else 6
    secondary_psms = psms[1:] if len(psms) > 1 else ()

    preprocess_priority: list[str] = ["original"]
    if enable_adaptive_threshold:
        preprocess_priority.append("adaptive_threshold")
    # gray/deskew are lower priority — added after secondary PSMs if budget remains.
    secondary_prep: list[str] = []
    if enable_gray_contrast:
        secondary_prep.append("gray_contrast")
    if enable_deskew:
        secondary_prep.append("deskew")

    plan: list[OcrVariantSpec] = []
    # Pass 1: primary preprocess variants with primary PSM (original, adaptive).
    for prep in preprocess_priority:
        if len(plan) >= max_calls:
            break
        plan.append(
            OcrVariantSpec(
                preprocess_variant=prep,
                psm=primary_psm,
                name=f"{prep}_psm{primary_psm}",
            )
        )
    # Pass 2: expand secondary PSMs on adaptive (or original).
    expand_prep = (
        "adaptive_threshold"
        if "adaptive_threshold" in preprocess_priority
        else preprocess_priority[0]
    )
    for psm in secondary_psms:
        if len(plan) >= max_calls:
            break
        name = f"{expand_prep}_psm{psm}"
        if any(s.name == name for s in plan):
            continue
        plan.append(
            OcrVariantSpec(preprocess_variant=expand_prep, psm=int(psm), name=name)
        )
    # Pass 3: leftover budget for gray/deskew with primary PSM.
    for prep in secondary_prep:
        if len(plan) >= max_calls:
            break
        plan.append(
            OcrVariantSpec(
                preprocess_variant=prep,
                psm=primary_psm,
                name=f"{prep}_psm{primary_psm}",
            )
        )
    return tuple(plan[:max_calls])


__all__ = [
    "VARIANT_PLAN_VERSION",
    "OcrVariantSpec",
    "build_ocr_variant_plan",
]
