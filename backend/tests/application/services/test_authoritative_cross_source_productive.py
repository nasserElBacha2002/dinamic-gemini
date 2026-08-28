"""Cross-source: authoritative D1 apply → TXT duplicate on shared counted ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.application.ports.issued_product_label_repository import IssuedProductLabel
from src.application.ports.job_source_asset_repository import JobSourceAssetLink
from src.application.services.image_processing.apply_authoritative_local_results import (
    ApplyAuthoritativeLocalResultsService,
)
from src.application.services.image_processing.processing_result_persister import (
    ProcessingResultPersister,
)
from src.application.services.local_csv_position_materializer import (
    LocalCsvPositionMaterializer,
    product_id_for_productive,
)
from src.application.services.product_labels.issued_product_label_resolver import (
    IssuedProductLabelResolver,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.authoritative_local_code_scan.entities import AuthoritativeLocalCodeScanResult
from src.domain.image_processing.job_asset_processing_state import (
    JobAssetProcessingState,
    JobAssetProcessingStatus,
)
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.local_csv_import.entities import LocalCsvProductiveResult
from src.domain.local_csv_import.sources import INGESTION_SOURCE_DINAMIC_SCANNER_TXT
from src.domain.product_labels.format import (
    build_product_label_payload,
    parse_product_label_payload,
)
from src.infrastructure.repositories.memory_authoritative_local_code_scan_repository import (
    MemoryAuthoritativeLocalCodeScanRepository,
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
from src.infrastructure.repositories.memory_job_asset_processing_state_repository import (
    MemoryJobAssetProcessingStateRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)

LABEL_ID = "A1B2C3D4E5"
NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)


def _inventory_repo() -> MemoryInventoryRepository:
    repo = MemoryInventoryRepository()
    repo.save(
        Inventory(
            id="inv-1",
            client_id="client-a",
            name="inv",
            status=InventoryStatus.DRAFT,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return repo


def _issued_resolver() -> IssuedProductLabelResolver:
    payload = build_product_label_payload(
        label_id=LABEL_ID, internal_code="SKU100", quantity=4
    )
    parsed = parse_product_label_payload(payload)
    repo = MemoryIssuedProductLabelRepository()
    repo.save(
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
    return IssuedProductLabelResolver(issued_repo=repo)


def _authoritative_row() -> AuthoritativeLocalCodeScanResult:
    return AuthoritativeLocalCodeScanResult(
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
        quantity_status="PRESENT",
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


def test_authoritative_valid_d1_claim_then_txt_skips_duplicate() -> None:
    """Real ApplyAuthoritative + ProcessingResultPersister claim; TXT materialize skips."""
    auth_repo = MemoryAuthoritativeLocalCodeScanRepository()
    auth_repo.create_authoritative_version(
        new_result=_authoritative_row(),
        expected_current_id=None,
        expected_row_version=None,
    )
    state_repo = MemoryJobAssetProcessingStateRepository()
    state_repo.save(
        JobAssetProcessingState(
            id="s1",
            job_id="job-1",
            asset_id="asset-1",
            status=JobAssetProcessingStatus.PENDING,
            created_at=NOW,
            updated_at=NOW,
            version=1,
        )
    )
    counted = MemoryInventoryCountedProductLabelRepository()
    saved_products: list = []
    product_repo = MagicMock()
    product_repo.save.side_effect = lambda p: saved_products.append(p)

    job_source = MagicMock()
    job_source.list_for_job.return_value = [
        JobSourceAssetLink(
            id="jsa-1",
            job_id="job-1",
            source_asset_id="asset-1",
            asset_role="primary",
            position_order=0,
            checksum=None,
            storage_key="key/a.jpg",
            mime_type="image/jpeg",
            size_bytes=100,
            width=None,
            height=None,
            stage=None,
            provider_request_id=None,
            created_at=NOW,
            original_filename="a.jpg",
        )
    ]
    source_repo = MagicMock()
    source_repo.get_by_id.return_value = SimpleNamespace(
        storage_path="path/a.jpg",
        storage_key="key/a.jpg",
        content_type="image/jpeg",
        file_size_bytes=100,
    )
    repos = SimpleNamespace(
        manual_coverage_repo=MagicMock(get_by_job_and_asset=MagicMock(return_value=None)),
        image_coverage_repo=MagicMock(has_results_for_asset=MagicMock(return_value=False)),
        position_repo=MagicMock(save=MagicMock()),
        product_record_repo=product_repo,
        evidence_repo=MagicMock(),
        result_evidence_repo=MagicMock(),
        counted_product_label_repo=counted,
    )
    uow = MagicMock()
    uow.repositories = repos
    uow.__enter__ = MagicMock(return_value=uow)
    uow.__exit__ = MagicMock(return_value=False)

    persister = ProcessingResultPersister(
        job_source_asset_repo=job_source,
        source_asset_repo=source_repo,
        clock=MagicMock(now=MagicMock(return_value=NOW)),
        unit_of_work_factory=lambda: uow,
    )
    svc = ApplyAuthoritativeLocalResultsService(
        authoritative_repo=auth_repo,
        result_persister=persister,
        state_repo=state_repo,
        clock=MagicMock(now=MagicMock(return_value=NOW)),
        enabled=True,
        inventory_repo=_inventory_repo(),
        issued_label_resolver=_issued_resolver(),
    )
    job = Job(
        id="job-1",
        target_type="aisle",
        target_id="aisle-1",
        job_type="process_aisle",
        status=JobStatus.RUNNING,
        payload_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    asset = SourceAsset(
        id="asset-1",
        aisle_id="aisle-1",
        type=SourceAssetType.PHOTO,
        original_filename="a.jpg",
        storage_path="/tmp/a.jpg",
        mime_type="image/jpeg",
        uploaded_at=NOW,
        upload_client_file_id="cf-1",
    )
    out = svc.apply_for_job(
        job=job, aisle_id="aisle-1", inventory_id="inv-1", assets=[asset]
    )
    assert out.applied == 1
    assert len(saved_products) == 1
    assert saved_products[0].label_id == LABEL_ID
    assert counted.get("aisle-1", LABEL_ID) is not None

    pos_repo = MemoryPositionRepository()
    prod_repo = MemoryProductRecordRepository()
    mat = LocalCsvPositionMaterializer(
        position_repo=pos_repo,
        product_record_repo=prod_repo,
        counted_product_label_repo=counted,
        issued_label_resolver=_issued_resolver(),
        inventory_repo=_inventory_repo(),
        client_position_label_repo=MemoryClientPositionLabelRepository(),
    )

    txt_row = LocalCsvProductiveResult(
        id="prod-txt",
        inventory_id="inv-1",
        aisle_id="aisle-1",
        import_id="imp-txt",
        import_row_id="row-txt",
        capture_session_id="sess-txt",
        capture_photo_id="txt-scan-1",
        client_file_id="txt-scan-1",
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
    written = mat.materialize([txt_row], now=NOW)
    assert written == 0
    assert prod_repo.get_by_id(product_id_for_productive("prod-txt")) is None
