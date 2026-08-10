"""Multi-product D1 consolidation (0..N per image)."""

from __future__ import annotations

from src.application.services.image_processing.code_detection_consolidator import (
    CodeConsolidationStatus,
    CodeDetectionConsolidator,
    CodeDetectionInput,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    LabelPayloadFormat,
    ParsedLabelPayload,
)
from src.domain.product_labels.format import build_product_label_payload


def _det(raw: str, idx: int = 0, *, code: str | None = None, qty: int | None = None) -> CodeDetectionInput:
    return CodeDetectionInput(
        symbology="CODE128",
        raw_value=raw,
        parsed=ParsedLabelPayload(
            format=LabelPayloadFormat.PIPE if code else LabelPayloadFormat.PLAIN,
            version=None,
            internal_code=code,
            quantity=qty,
            raw_value=raw,
        ),
        detection_index=idx,
    )


def test_zero_products() -> None:
    result = CodeDetectionConsolidator().consolidate([])
    assert result.status is CodeConsolidationStatus.NO_DETECTIONS
    assert result.product_results == ()


def test_one_d1_product() -> None:
    payload = build_product_label_payload(
        label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4
    )
    result = CodeDetectionConsolidator().consolidate([_det(payload)])
    assert result.status is CodeConsolidationStatus.RESOLVED
    assert len(result.product_results) == 1
    assert result.product_results[0].label_id == "A1B2C3D4E5"


def test_two_d1_products_same_image() -> None:
    a = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    b = build_product_label_payload(label_id="FGHJKMNPQR", internal_code="SKU200", quantity=2)
    result = CodeDetectionConsolidator().consolidate([_det(a, 0), _det(b, 1)])
    assert result.status is CodeConsolidationStatus.RESOLVED_MULTI
    assert len(result.product_results) == 2
    ids = {p.label_id for p in result.product_results}
    assert ids == {"A1B2C3D4E5", "FGHJKMNPQR"}


def test_five_d1_products() -> None:
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    dets = []
    for i in range(5):
        lid = "".join(alphabet[(i + j) % len(alphabet)] for j in range(10))
        dets.append(
            _det(
                build_product_label_payload(label_id=lid, internal_code=f"SKU{i}", quantity=i + 1),
                i,
            )
        )
    result = CodeDetectionConsolidator().consolidate(dets)
    assert len(result.product_results) == 5


def test_intra_image_dedupe_by_label_id() -> None:
    a = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    result = CodeDetectionConsolidator().consolidate([_det(a, 0), _det(a, 1)])
    assert len(result.product_results) == 1
    assert result.product_results[0].duplicate_detection_count == 2


def test_same_sku_different_label_ids() -> None:
    a = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU100", quantity=4)
    b = build_product_label_payload(label_id="FGHJKMNPQR", internal_code="SKU100", quantity=6)
    result = CodeDetectionConsolidator().consolidate([_det(a), _det(b, 1)])
    assert len(result.product_results) == 2


def test_checksum_failed_no_item() -> None:
    bad = "D1|A1B2C3D4E5|SKU100|5|6"
    result = CodeDetectionConsolidator().consolidate([_det(bad)])
    assert result.status is CodeConsolidationStatus.NO_VALID_CODE
    assert result.product_results == ()
    assert any(r.validation_status == "CHECKSUM_FAILED" for r in result.rejections)


def test_external_ean_no_item() -> None:
    result = CodeDetectionConsolidator().consolidate([_det("7790001234567")])
    assert result.product_results == ()
    assert result.status in (
        CodeConsolidationStatus.NO_VALID_CODE,
        CodeConsolidationStatus.MISSING_QUANTITY,
    )


def test_legacy_pipe_single() -> None:
    result = CodeDetectionConsolidator().consolidate(
        [_det("SKU100|4", code="SKU100", qty=4)]
    )
    assert result.status is CodeConsolidationStatus.RESOLVED
    assert result.internal_code == "SKU100"
    assert result.quantity == 4
    assert result.product_results == ()


def test_two_valid_plus_one_invalid_keeps_two() -> None:
    import json
    from pathlib import Path

    a = build_product_label_payload(label_id="A1B2C3D4E5", internal_code="SKU_A", quantity=1)
    b = build_product_label_payload(label_id="FGHJKMNPQR", internal_code="SKU_B", quantity=2)
    vectors = json.loads(
        Path(__file__)
        .resolve()
        .parents[5]
        .joinpath("contracts/product-labels/v1/checksum-vectors.json")
        .read_text(encoding="utf-8")
    )
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    result = CodeDetectionConsolidator().consolidate(
        [_det(a, 0), _det(b, 1), _det(bad, 2)]
    )
    assert result.status is CodeConsolidationStatus.RESOLVED_MULTI
    assert len(result.product_results) == 2
    assert "D1_PARTIAL_REJECTIONS" in result.warnings
    assert len(result.rejections) >= 1


def test_invalid_d1_plus_legacy_barcode_yields_zero() -> None:
    import json
    from pathlib import Path

    vectors = json.loads(
        Path(__file__)
        .resolve()
        .parents[5]
        .joinpath("contracts/product-labels/v1/checksum-vectors.json")
        .read_text(encoding="utf-8")
    )
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    result = CodeDetectionConsolidator().consolidate(
        [_det(bad, 0), _det("SKU123|1000", 1, code="SKU123", qty=1000)]
    )
    assert result.status is CodeConsolidationStatus.NO_VALID_CODE
    assert result.product_results == ()
    assert "D1_CANDIDATES_FAILED" in result.warnings
    assert result.internal_code is None
