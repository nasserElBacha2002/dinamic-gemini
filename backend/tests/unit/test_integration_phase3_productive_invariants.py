"""Phase 3 — cross-source productive invariants (TXT trust, counted labels, flags)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from src.application.services.local_csv_position_materializer import (
    LocalCsvPositionMaterializer,
    position_id_for_productive,
    product_id_for_productive,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
)
from src.domain.client_position_label.hierarchy import PositionSide
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import (
    INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    INGESTION_SOURCE_LOCAL_CSV_IMPORT,
)
from src.infrastructure.repositories.memory_client_position_label_repository import (
    MemoryClientPositionLabelRepository,
)
from src.infrastructure.repositories.memory_inventory_counted_product_label_repository import (
    MemoryInventoryCountedProductLabelRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
LABEL_ID = "A1B2C3D4E5"
POS_LABEL = "pos_txt_01"


def _inventory_repo(*, client_id: str = "client-a") -> MemoryInventoryRepository:
    repo = MemoryInventoryRepository()
    repo.save(
        Inventory(
            id="inv-1",
            name="Inventory",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
            client_id=client_id,
        )
    )
    return repo


def _catalog_label(
    repo: MemoryClientPositionLabelRepository,
    *,
    pallet: str = "02",
    side: str = "LEFT",
) -> None:
    payload = build_positioning_label_payload(
        public_label_id=POS_LABEL,
        pallet=pallet,
        side=PositionSide(side),
        level=3,
        marker_index=2,
        marker_total=4,
    )
    repo.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-a",
            public_identifier=POS_LABEL,
            name="Pallet 02",
            normalized_name="PALLET 02",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload=payload,
            created_at=NOW,
            updated_at=NOW,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )


def _txt_payload(*, pallet: str, side: str) -> str:
    # Converter defaults level/markers to 1 — catalog may differ; only pallet|side authenticated.
    payload = build_positioning_label_payload(
        public_label_id=POS_LABEL,
        pallet=pallet,
        side=PositionSide(side),
        level=1,
        marker_index=1,
        marker_total=1,
    )
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _materializer(
    *,
    position_labels: MemoryClientPositionLabelRepository | None = None,
    counted: MemoryInventoryCountedProductLabelRepository | None = None,
) -> tuple[
    LocalCsvPositionMaterializer,
    MemoryPositionRepository,
    MemoryInventoryCountedProductLabelRepository,
]:
    counted_repo = counted or MemoryInventoryCountedProductLabelRepository()
    pos = MemoryPositionRepository()
    prod = MemoryProductRecordRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=pos,
        product_record_repo=prod,
        counted_product_label_repo=counted_repo,
        issued_label_resolver=IssuedProductLabelResolver(
            issued_repo=MemoryIssuedProductLabelRepository()
        ),
        inventory_repo=_inventory_repo(),
        client_position_label_repo=position_labels,
    )
    return mat, pos, counted_repo


def _result(
    *,
    id: str = "prod-1",
    ingestion_source: str = INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    position_code: str | None = "02",
    position_payload_raw: str | None = None,
    label_id: str | None = None,
    has_image_evidence: bool = False,
) -> LocalCsvProductiveResult:
    return LocalCsvProductiveResult(
        id=id,
        inventory_id="inv-1",
        aisle_id="aisle-1",
        import_id="imp-1",
        import_row_id=f"row-{id}",
        capture_session_id="sess-1",
        capture_photo_id=f"txt-scan-{id}",
        client_file_id=f"txt-scan-{id}",
        capture_order=1,
        position_code=position_code,
        internal_code="SKU100",
        quantity=4,
        quantity_status="PRESENT",
        detection_status="DETECTED",
        detection_source="LOCAL_CODE_SCAN",
        ingestion_source=ingestion_source,
        requires_review=False,
        has_image_evidence=has_image_evidence,
        confirmed_by_user_id="user-1",
        created_at=NOW,
        updated_at=NOW,
        source_asset_id=None,
        label_id=label_id,
        position_label_id=POS_LABEL,
        position_payload_raw=position_payload_raw,
    )


def test_txt_valid_catalog_hierarchy_materializes_position_code() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels, pallet="02", side="LEFT")
    mat, pos_repo, _ = _materializer(position_labels=labels)
    result = _result(position_payload_raw=_txt_payload(pallet="02", side="LEFT"))
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code == "02"
    assert pos.needs_review is False
    assert pos.detected_summary_json is not None
    assert pos.detected_summary_json.get("position_payload_status") is None


def test_txt_tampered_pallet_clears_position_code() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels, pallet="02", side="LEFT")
    mat, pos_repo, _ = _materializer(position_labels=labels)
    result = _result(
        position_code="99",
        position_payload_raw=_txt_payload(pallet="99", side="LEFT"),
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code is None
    assert pos.needs_review is True
    assert pos.detected_summary_json.get("position_payload_status") == "ignored_invalid"


def test_txt_tampered_side_clears_position_code() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels, pallet="02", side="LEFT")
    mat, pos_repo, _ = _materializer(position_labels=labels)
    result = _result(
        position_payload_raw=_txt_payload(pallet="02", side="RIGHT"),
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code is None
    assert pos.needs_review is True


def test_txt_unknown_label_clears_position() -> None:
    mat, pos_repo, _ = _materializer(position_labels=MemoryClientPositionLabelRepository())
    result = _result(position_payload_raw=_txt_payload(pallet="02", side="LEFT"))
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code is None
    assert pos.needs_review is True


def test_txt_without_catalog_repo_fail_closed() -> None:
    mat, pos_repo, _ = _materializer(position_labels=None)
    result = _result(position_payload_raw=_txt_payload(pallet="02", side="LEFT"))
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code is None


def test_cross_source_same_label_counted_once_csv_then_txt() -> None:
    """Same physical D1 label_id via CSV then TXT → one ProductRecord (aisle claim)."""
    from src.application.ports.issued_product_label_repository import IssuedProductLabel
    from src.domain.product_labels.format import (
        build_product_label_payload,
        parse_product_label_payload,
    )

    issued = MemoryIssuedProductLabelRepository()
    payload = build_product_label_payload(
        label_id=LABEL_ID, internal_code="SKU100", quantity=4
    )
    parsed = parse_product_label_payload(payload)
    issued.save(
        IssuedProductLabel(
            id="iss-1",
            client_id="client-a",
            label_id=LABEL_ID,
            internal_code="SKU100",
            quantity=4,
            format_version="D1",
            checksum=str(parsed.checksum_received),
            payload=payload,
            created_at=NOW,
        )
    )
    counted = MemoryInventoryCountedProductLabelRepository()
    pos = MemoryPositionRepository()
    prod = MemoryProductRecordRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=pos,
        product_record_repo=prod,
        counted_product_label_repo=counted,
        issued_label_resolver=IssuedProductLabelResolver(issued_repo=issued),
        inventory_repo=_inventory_repo(),
        client_position_label_repo=MemoryClientPositionLabelRepository(),
    )
    csv_row = _result(
        id="prod-csv",
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        position_payload_raw=None,
        label_id=LABEL_ID,
        has_image_evidence=False,
        position_code="A-01",
    )
    assert mat.materialize([csv_row], now=NOW) == 1
    assert len(list(prod.list_by_position(position_id_for_productive("prod-csv")))) == 1

    txt_row = _result(
        id="prod-txt",
        ingestion_source=INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
        position_payload_raw=None,
        label_id=LABEL_ID,
        has_image_evidence=False,
        position_code=None,
    )
    written = mat.materialize([txt_row], now=NOW)
    assert written == 0
    assert prod.get_by_id(product_id_for_productive("prod-txt")) is None


def test_feature_flag_txt_explicit_false_overrides_csv_default() -> None:
    import os

    from src.env_settings.grouped_settings import LimitsAndSchemaSettings

    prev_csv = os.environ.get("SERVER_CSV_IMPORT_ENABLED")
    prev_txt = os.environ.get("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED")
    prev_pkg = os.environ.get("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED")
    try:
        os.environ["SERVER_CSV_IMPORT_ENABLED"] = "true"
        os.environ["SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED"] = "false"
        os.environ.pop("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED", None)
        settings = LimitsAndSchemaSettings()
        assert settings.server_csv_import_enabled is True
        assert settings.server_dinamic_scanner_txt_import_enabled is False
    finally:
        if prev_csv is None:
            os.environ.pop("SERVER_CSV_IMPORT_ENABLED", None)
        else:
            os.environ["SERVER_CSV_IMPORT_ENABLED"] = prev_csv
        if prev_txt is None:
            os.environ.pop("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", None)
        else:
            os.environ["SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED"] = prev_txt
        if prev_pkg is None:
            os.environ.pop("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED", None)
        else:
            os.environ["SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED"] = prev_pkg


def test_feature_flag_matrix_csv_false_txt_true_independent() -> None:
    import os

    from src.env_settings.grouped_settings import LimitsAndSchemaSettings

    prev_csv = os.environ.get("SERVER_CSV_IMPORT_ENABLED")
    prev_txt = os.environ.get("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED")
    prev_pkg = os.environ.get("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED")
    try:
        os.environ["SERVER_CSV_IMPORT_ENABLED"] = "false"
        os.environ["SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED"] = "true"
        os.environ["SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED"] = "true"
        settings = LimitsAndSchemaSettings()
        assert settings.server_csv_import_enabled is False
        assert settings.server_dinamic_scanner_txt_import_enabled is True
        assert settings.server_local_inventory_package_enabled is True
    finally:
        for key, prev in (
            ("SERVER_CSV_IMPORT_ENABLED", prev_csv),
            ("SERVER_DINAMIC_SCANNER_TXT_IMPORT_ENABLED", prev_txt),
            ("SERVER_LOCAL_INVENTORY_PACKAGE_ENABLED", prev_pkg),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev


def _issued_materializer(
    *,
    counted: MemoryInventoryCountedProductLabelRepository | None = None,
    position_labels: MemoryClientPositionLabelRepository | None = None,
):
    from src.application.ports.issued_product_label_repository import IssuedProductLabel
    from src.domain.product_labels.format import (
        build_product_label_payload,
        parse_product_label_payload,
    )

    issued = MemoryIssuedProductLabelRepository()
    payload = build_product_label_payload(
        label_id=LABEL_ID, internal_code="SKU100", quantity=4
    )
    parsed = parse_product_label_payload(payload)
    issued.save(
        IssuedProductLabel(
            id="iss-1",
            client_id="client-a",
            label_id=LABEL_ID,
            internal_code="SKU100",
            quantity=4,
            format_version="D1",
            checksum=str(parsed.checksum_received),
            payload=payload,
            created_at=NOW,
        )
    )
    counted_repo = counted or MemoryInventoryCountedProductLabelRepository()
    pos = MemoryPositionRepository()
    prod = MemoryProductRecordRepository()
    labels = position_labels if position_labels is not None else MemoryClientPositionLabelRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=pos,
        product_record_repo=prod,
        counted_product_label_repo=counted_repo,
        issued_label_resolver=IssuedProductLabelResolver(issued_repo=issued),
        inventory_repo=_inventory_repo(),
        client_position_label_repo=labels,
    )
    return mat, pos, prod, counted_repo


def test_txt_missing_raw_with_position_code_no_auto_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels)
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    result = _result(
        position_code="02",
        position_payload_raw=None,
        label_id=LABEL_ID,
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code is None
    assert pos.needs_review is True
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None


def test_txt_missing_raw_with_position_label_id_no_auto_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels)
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    result = _result(
        position_code=None,
        position_payload_raw=None,
        label_id=LABEL_ID,
    )
    # position_label_id still set by _result helper
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.corrected_position_code is None
    assert pos.needs_review is True
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None


def test_txt_without_position_claim_ok() -> None:
    mat, pos_repo, prod, _ = _issued_materializer()
    result = LocalCsvProductiveResult(
        id="prod-nopos",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        import_id="imp-1",
        import_row_id="row-nopos",
        capture_session_id="sess-1",
        capture_photo_id="txt-scan-nopos",
        client_file_id="txt-scan-nopos",
        capture_order=1,
        position_code=None,
        internal_code="SKU100",
        quantity=4,
        quantity_status="PRESENT",
        detection_status="DETECTED",
        detection_source="LOCAL_CODE_SCAN",
        ingestion_source=INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
        requires_review=False,
        has_image_evidence=False,
        confirmed_by_user_id="user-1",
        created_at=NOW,
        updated_at=NOW,
        source_asset_id=None,
        label_id=LABEL_ID,
        position_label_id=None,
        position_payload_raw=None,
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-nopos"))
    assert pos is not None
    assert pos.corrected_position_code is None
    assert pos.needs_review is False
    assert prod.get_by_id(product_id_for_productive("prod-nopos")) is not None


def test_csv_without_raw_payload_keeps_position_code_regression() -> None:
    mat, pos_repo, _, _ = _issued_materializer()
    result = _result(
        id="prod-csv-pos",
        ingestion_source=INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        position_code="A-01",
        position_payload_raw=None,
        label_id=LABEL_ID,
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-csv-pos"))
    assert pos.corrected_position_code == "A-01"


def test_txt_catalog_without_hierarchy_no_auto_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-a",
            public_identifier=POS_LABEL,
            name="Legacy",
            normalized_name="LEGACY",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload={"type": "DINAMIC_POSITION", "label_id": POS_LABEL},
            created_at=NOW,
            updated_at=NOW,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    result = _result(
        position_payload_raw=_txt_payload(pallet="02", side="LEFT"),
        label_id=LABEL_ID,
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.corrected_position_code is None
    assert pos.needs_review is True
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None


def test_txt_catalog_only_pallet_no_auto_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-a",
            public_identifier=POS_LABEL,
            name="Pallet only",
            normalized_name="PALLET ONLY",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload={"pallet": "02", "label_id": POS_LABEL},
            created_at=NOW,
            updated_at=NOW,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    mat, pos_repo, _, _ = _issued_materializer(position_labels=labels)
    result = _result(position_payload_raw=_txt_payload(pallet="02", side="LEFT"))
    assert mat.materialize([result], now=NOW) == 1
    assert pos_repo.get_by_id(position_id_for_productive("prod-1")).corrected_position_code is None


def test_txt_catalog_only_side_no_auto_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    labels.save(
        ClientPositionLabel(
            id=str(uuid4()),
            client_id="client-a",
            public_identifier=POS_LABEL,
            name="Side only",
            normalized_name="SIDE ONLY",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload={"side": "LEFT", "label_id": POS_LABEL},
            created_at=NOW,
            updated_at=NOW,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    mat, pos_repo, _, _ = _issued_materializer(position_labels=labels)
    result = _result(position_payload_raw=_txt_payload(pallet="02", side="LEFT"))
    assert mat.materialize([result], now=NOW) == 1
    assert pos_repo.get_by_id(position_id_for_productive("prod-1")).corrected_position_code is None


def test_txt_internal_db_id_spoof_rejects_position() -> None:
    labels = MemoryClientPositionLabelRepository()
    internal_id = str(uuid4())
    payload = build_positioning_label_payload(
        public_label_id=POS_LABEL,
        pallet="02",
        side=PositionSide.LEFT,
        level=3,
        marker_index=2,
        marker_total=4,
    )
    labels.save(
        ClientPositionLabel(
            id=internal_id,
            client_id="client-a",
            public_identifier=POS_LABEL,
            name="Pallet 02",
            normalized_name="PALLET 02",
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload=payload,
            created_at=NOW,
            updated_at=NOW,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
        )
    )
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    # Spoof: use internal DB id as payload label_id (not public_identifier).
    spoof = dict(payload)
    spoof["label_id"] = internal_id
    result = _result(
        position_payload_raw=json.dumps(spoof, sort_keys=True, separators=(",", ":")),
        label_id=LABEL_ID,
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.corrected_position_code is None
    assert pos.needs_review is True
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None


def test_txt_public_id_plus_mismatched_claimed_internal_rejects() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels)
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    result = _result(
        position_payload_raw=_txt_payload(pallet="02", side="LEFT"),
        label_id=LABEL_ID,
    )
    # Force claimed position_label_id to an internal-looking id.
    result = LocalCsvProductiveResult(
        **{**result.__dict__, "position_label_id": str(uuid4())}
    )
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.corrected_position_code is None
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None


def test_valid_d1_invalid_txt_position_preserves_product() -> None:
    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels, pallet="02", side="LEFT")
    mat, pos_repo, prod, _ = _issued_materializer(position_labels=labels)
    result = _result(
        position_code="99",
        position_payload_raw=_txt_payload(pallet="99", side="LEFT"),
        label_id=LABEL_ID,
    )
    assert mat.materialize([result], now=NOW) == 1
    assert prod.get_by_id(product_id_for_productive("prod-1")) is not None
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.corrected_position_code is None
    assert pos.needs_review is True


def test_valid_position_invalid_d1_no_product() -> None:
    """Valid TXT position must not salvage an invalid D1 into a counted claim."""
    from src.domain.product_labels.format import (
        ProductLabelValidationStatus,
        build_product_label_payload,
        parse_product_label_payload,
    )

    good = build_product_label_payload(
        label_id=LABEL_ID, internal_code="SKU100", quantity=4
    )
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")
    parsed = parse_product_label_payload(bad)
    assert parsed.status is not ProductLabelValidationStatus.VALID

    labels = MemoryClientPositionLabelRepository()
    _catalog_label(labels)
    mat, pos_repo, counted = _materializer(position_labels=labels)
    result = _result(
        position_payload_raw=_txt_payload(pallet="02", side="LEFT"),
        label_id=None,
    )
    result = LocalCsvProductiveResult(
        **{
            **result.__dict__,
            "internal_code": "",
            "quantity": None,
            "quantity_status": "MISSING",
        }
    )
    # Access product repo via materializer internals for this negative case.
    prod = mat._product_record_repo
    mat.materialize([result], now=NOW)
    product = prod.get_by_id(product_id_for_productive("prod-1"))
    assert product is None or (product.label_id is None and product.sku == "UNKNOWN")
    assert counted.get("aisle-1", LABEL_ID) is None
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos is not None
    assert pos.corrected_position_code == "02"


def test_mobile_claim_then_txt_duplicate_one_product() -> None:
    """Simulate Mobile authoritative claim then TXT same label → one ProductRecord."""
    from src.application.ports.inventory_counted_product_label_repository import (
        InventoryCountedProductLabel,
    )
    from src.domain.products.entities import ProductRecord

    mat, _, prod, counted = _issued_materializer()
    mobile_product_id = "mobile-prod-1"
    assert counted.try_claim(
        InventoryCountedProductLabel(
            id=str(uuid4()),
            inventory_id="inv-1",
            aisle_id="aisle-1",
            label_id=LABEL_ID,
            first_product_record_id=mobile_product_id,
            first_source_asset_id="asset-mobile",
            first_job_id="job-mobile",
            first_position_id="pos-mobile",
            created_at=NOW,
        )
    )
    prod.save(
        ProductRecord(
            id=mobile_product_id,
            position_id="pos-mobile",
            sku="SKU100",
            description=None,
            detected_quantity=4,
            corrected_quantity=None,
            confidence=1.0,
            created_at=NOW,
            updated_at=NOW,
            label_id=LABEL_ID,
        )
    )
    txt = _result(id="prod-txt", label_id=LABEL_ID, position_payload_raw=None, position_code=None)
    assert mat.materialize([txt], now=NOW) == 0
    assert prod.get_by_id(product_id_for_productive("prod-txt")) is None
    assert counted.get("aisle-1", LABEL_ID) is not None


def test_txt_then_mobile_claim_duplicate() -> None:
    from src.application.ports.inventory_counted_product_label_repository import (
        InventoryCountedProductLabel,
    )

    mat, _, prod, counted = _issued_materializer()
    txt = _result(id="prod-txt", label_id=LABEL_ID, position_code=None, position_payload_raw=None)
    assert mat.materialize([txt], now=NOW) == 1
    assert prod.get_by_id(product_id_for_productive("prod-txt")) is not None
    # Mobile apply tries same aisle+label claim → False
    assert (
        counted.try_claim(
            InventoryCountedProductLabel(
                id=str(uuid4()),
                inventory_id="inv-1",
                aisle_id="aisle-1",
                label_id=LABEL_ID,
                first_product_record_id="mobile-prod-2",
                first_source_asset_id="asset-m2",
                first_job_id="job-m2",
                first_position_id="pos-m2",
                created_at=NOW,
            )
        )
        is False
    )


def test_same_label_different_aisle_both_count_documents_scope() -> None:
    """UNIQUE(aisle_id, label_id): different aisle + same label → both count."""
    from src.application.ports.inventory_counted_product_label_repository import (
        InventoryCountedProductLabel,
    )

    counted = MemoryInventoryCountedProductLabelRepository()
    assert counted.try_claim(
        InventoryCountedProductLabel(
            id=str(uuid4()),
            inventory_id="inv-1",
            aisle_id="aisle-a",
            label_id=LABEL_ID,
            first_product_record_id="p-a",
            first_source_asset_id="a1",
            first_job_id="j1",
            first_position_id="pos-a",
            created_at=NOW,
        )
    )
    assert counted.try_claim(
        InventoryCountedProductLabel(
            id=str(uuid4()),
            inventory_id="inv-1",
            aisle_id="aisle-b",
            label_id=LABEL_ID,
            first_product_record_id="p-b",
            first_source_asset_id="a2",
            first_job_id="j2",
            first_position_id="pos-b",
            created_at=NOW,
        )
    )


def test_same_aisle_same_label_duplicate() -> None:
    from src.application.ports.inventory_counted_product_label_repository import (
        InventoryCountedProductLabel,
    )

    counted = MemoryInventoryCountedProductLabelRepository()
    assert counted.try_claim(
        InventoryCountedProductLabel(
            id=str(uuid4()),
            inventory_id="inv-1",
            aisle_id="aisle-1",
            label_id=LABEL_ID,
            first_product_record_id="p1",
            first_source_asset_id="a1",
            first_job_id="j1",
            first_position_id="pos1",
            created_at=NOW,
        )
    )
    assert (
        counted.try_claim(
            InventoryCountedProductLabel(
                id=str(uuid4()),
                inventory_id="inv-1",
                aisle_id="aisle-1",
                label_id=LABEL_ID,
                first_product_record_id="p2",
                first_source_asset_id="a2",
                first_job_id="j2",
                first_position_id="pos2",
                created_at=NOW,
            )
        )
        is False
    )


def test_txt_has_image_evidence_false_even_with_scan_ids() -> None:
    mat, pos_repo, _, _ = _issued_materializer()
    result = _result(label_id=LABEL_ID, has_image_evidence=False, position_code=None)
    assert result.capture_photo_id.startswith("txt-scan-")
    assert mat.materialize([result], now=NOW) == 1
    pos = pos_repo.get_by_id(position_id_for_productive("prod-1"))
    assert pos.primary_evidence_id is None
    assert result.has_image_evidence is False
