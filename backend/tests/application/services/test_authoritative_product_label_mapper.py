"""Authoritative → ProcessedProductLabel mapper (D1 trust boundary)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.issued_product_label_repository import IssuedProductLabel
from src.application.services.image_processing.authoritative_product_label_mapper import (
    authoritative_blocks_legacy_persist_fallback,
    build_product_results_for_authoritative_row,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.authoritative_local_code_scan.entities import (
    AuthoritativeLocalCodeScanResult,
    AuthoritativeQuantityStatus,
)
from src.domain.product_labels.format import (
    build_product_label_payload,
    parse_product_label_payload,
)
from src.domain.product_labels.processed import ProductLabelOutcomeStatus
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)

LABEL_ID = "A1B2C3D4E5"
NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)


def _row(**overrides) -> AuthoritativeLocalCodeScanResult:
    base = dict(
        id="res-1",
        asset_id="asset-1",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        client_file_id="cf-1",
        result_version=1,
        supersedes_result_id=None,
        is_current=True,
        internal_code="SKU100",
        quantity=4,
        quantity_status=AuthoritativeQuantityStatus.PRESENT.value,
        source="LOCAL_CODE_SCAN",
        detected_internal_code="SKU100",
        detected_quantity=4,
        detected_symbology="QR_CODE",
        parser_version="1",
        detector_version="mlkit",
        prepared_asset_sha256="sha256:" + ("b" * 64),
        content_hash="sha256:" + ("c" * 64),
        confirmed_by="user-1",
        client_confirmed_at=NOW,
        server_confirmed_at=NOW,
        server_received_at=NOW,
        confirmed_at=NOW,
        applied_job_id=None,
        applied_at=None,
        row_version=1,
        schema_version="1",
        created_at=NOW,
        updated_at=NOW,
        label_id=LABEL_ID,
    )
    base.update(overrides)
    return AuthoritativeLocalCodeScanResult(**base)


def _seed_issued(*, sku: str = "SKU100", qty: int = 4) -> IssuedProductLabelResolver:
    payload = build_product_label_payload(
        label_id=LABEL_ID, internal_code=sku, quantity=qty
    )
    parsed = parse_product_label_payload(payload)
    repo = MemoryIssuedProductLabelRepository()
    repo.save(
        IssuedProductLabel(
            id="iss-1",
            client_id="client-a",
            label_id=LABEL_ID,
            internal_code=sku,
            quantity=qty,
            format_version="D1",
            checksum=str(parsed.checksum_received),
            payload=payload,
            created_at=NOW,
        )
    )
    return IssuedProductLabelResolver(issued_repo=repo)


def test_d1_present_valid_resolves_via_issued_registry() -> None:
    resolver = _seed_issued()
    products = build_product_results_for_authoritative_row(
        _row(),
        client_id="client-a",
        issued_resolver=resolver,
    )
    assert len(products) == 1
    p = products[0]
    assert p.validation_status is ProductLabelOutcomeStatus.VALID
    assert p.label_id == LABEL_ID
    assert p.internal_code == "SKU100"
    assert p.quantity == 4
    assert p.checksum is not None


def test_d1_label_id_with_missing_quantity_not_valid() -> None:
    products = build_product_results_for_authoritative_row(
        _row(quantity=None, quantity_status=AuthoritativeQuantityStatus.MISSING.value),
        client_id="client-a",
        issued_resolver=_seed_issued(),
    )
    assert len(products) == 1
    assert products[0].validation_status is ProductLabelOutcomeStatus.QUANTITY_INVALID
    assert authoritative_blocks_legacy_persist_fallback(_row(quantity=None, quantity_status="MISSING"), products)


def test_legacy_without_label_id_missing_quantity_stays_legacy() -> None:
    products = build_product_results_for_authoritative_row(
        _row(
            label_id=None,
            quantity=None,
            quantity_status=AuthoritativeQuantityStatus.MISSING.value,
        ),
        client_id="client-a",
        issued_resolver=_seed_issued(),
    )
    assert len(products) == 1
    assert products[0].validation_status is ProductLabelOutcomeStatus.VALID
    assert products[0].quantity == 0
    assert products[0].detail == "legacy_missing_quantity"
    assert not authoritative_blocks_legacy_persist_fallback(
        _row(label_id=None, quantity=None, quantity_status="MISSING"), products
    )


def test_manual_correction_strips_label_id_and_never_d1_valid() -> None:
    products = build_product_results_for_authoritative_row(
        _row(source="LOCAL_MANUAL_CORRECTION", label_id=LABEL_ID),
        client_id="client-a",
        issued_resolver=_seed_issued(),
    )
    assert len(products) == 1
    p = products[0]
    assert p.label_id is None
    assert p.validation_status is ProductLabelOutcomeStatus.VALID
    assert p.detail == "authoritative_manual_correction"


def test_sku_mismatch_rejected() -> None:
    resolver = _seed_issued(sku="SKU100", qty=4)
    products = build_product_results_for_authoritative_row(
        _row(internal_code="SKU999"),
        client_id="client-a",
        issued_resolver=resolver,
    )
    assert len(products) == 1
    assert products[0].validation_status is ProductLabelOutcomeStatus.PAYLOAD_MISMATCH


def test_qty_mismatch_rejected() -> None:
    resolver = _seed_issued()
    products = build_product_results_for_authoritative_row(
        _row(quantity=99),
        client_id="client-a",
        issued_resolver=resolver,
    )
    assert len(products) == 1
    assert products[0].validation_status is ProductLabelOutcomeStatus.PAYLOAD_MISMATCH


def test_unknown_label_id_rejected() -> None:
    resolver = _seed_issued()
    products = build_product_results_for_authoritative_row(
        _row(label_id="FGHJKMNPQR"),
        client_id="client-a",
        issued_resolver=resolver,
    )
    assert len(products) == 1
    assert products[0].validation_status is ProductLabelOutcomeStatus.UNKNOWN_LABEL
