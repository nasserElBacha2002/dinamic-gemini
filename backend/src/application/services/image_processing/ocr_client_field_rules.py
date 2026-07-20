"""Minimal per-client OCR field-priority rules (Phase 4; not full Phase 6 admin profiles)."""

from __future__ import annotations

from src.application.services.image_processing.ocr_result_normalizer import OcrClientFieldRules


def parse_ean_first_client_ids(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in str(raw).split(",") if part.strip())


def resolve_ocr_client_field_rules(
    *,
    client_id: str | None,
    ean_first_client_ids: frozenset[str] | str | None = None,
    global_prefer_ean: bool = False,
) -> OcrClientFieldRules:
    """Resolve OCR field priority for one client without hardcoding client names.

    - Clients listed in ``INTERNAL_OCR_EAN_FIRST_CLIENT_IDS`` get EAN-first priority
      (MASOL-style mapping).
    - Everyone else defaults to labeled ``codigo`` / article / product before bare EAN,
      unless the deprecated global ``INTERNAL_OCR_PREFER_EAN_AS_INTERNAL_CODE`` is true.
    """
    ids = (
        ean_first_client_ids
        if isinstance(ean_first_client_ids, frozenset)
        else parse_ean_first_client_ids(ean_first_client_ids)
    )
    cid = (client_id or "").strip()
    if cid and cid in ids:
        return OcrClientFieldRules(
            profile_key="ean_first",
            profile_version="1",
            prefer_ean_as_internal_code=True,
            internal_code_priority=(
                "ean_label",
                "bare_ean",
                "label",
                "article_label",
                "product_label",
            ),
        )
    if global_prefer_ean:
        return OcrClientFieldRules(
            profile_key="global_ean_first",
            profile_version="1",
            prefer_ean_as_internal_code=True,
            internal_code_priority=(
                "ean_label",
                "bare_ean",
                "label",
                "article_label",
                "product_label",
            ),
        )
    return OcrClientFieldRules(
        profile_key="default",
        profile_version="1",
        prefer_ean_as_internal_code=False,
        internal_code_priority=(
            "label",
            "article_label",
            "product_label",
            "ean_label",
            "bare_ean",
        ),
    )


def ocr_client_rules_snapshot(rules: OcrClientFieldRules) -> dict:
    return {
        "client_rule_key": rules.profile_key,
        "client_rule_version": rules.profile_version,
        "internal_code_priority": list(rules.internal_code_priority),
        "prefer_ean_as_internal_code": rules.prefer_ean_as_internal_code,
        "required_fields": ["internal_code", "quantity"],
    }
