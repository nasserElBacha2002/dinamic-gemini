"""Unit tests for UpsertPreliminaryDetectionUseCase (Phase 4 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.ports.mobile_preliminary_detection_repository import (
    PreliminaryUniqueViolationError,
)
from src.application.services.preliminary_detection_content import (
    PreliminaryDetectionContentCanonicalizer,
)
from src.application.use_cases.aisles.upsert_preliminary_detection import (
    PRELIMINARY_IDEMPOTENCY_CONFLICT,
    PositionReferenceEvidenceV2,
    PositionSignatureEvidenceV2,
    PreliminaryDetectionIngestDisabledError,
    UpsertPreliminaryDetectionCommand,
    UpsertPreliminaryDetectionUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.domain.mobile_preliminary_detections.entities import MobilePreliminaryDetection
from src.domain.position_recognition import (
    CanonicalPositionRecognition,
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_inventory_repository import (
    MemoryInventoryRepository,
)
from src.infrastructure.repositories.memory_mobile_preliminary_detection_repository import (
    MemoryMobilePreliminaryDetectionRepository,
)
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc)


def _aisle() -> Aisle:
    return Aisle(
        id="aisle-1",
        inventory_id="inv-1",
        code="A1",
        status=AisleStatus.CREATED,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _asset(*, aisle_id: str = "aisle-1", client_file_id: str = "cf-1") -> SourceAsset:
    return SourceAsset(
        id="asset-1",
        aisle_id=aisle_id,
        type=SourceAssetType.PHOTO,
        original_filename="x.jpg",
        storage_path="/tmp/x.jpg",
        mime_type="image/jpeg",
        uploaded_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        upload_client_file_id=client_file_id,
    )


def _inventory(*, client_id: str | None = "client-server") -> Inventory:
    return Inventory(
        id="inv-1",
        name="Inventory",
        status=InventoryStatus.DRAFT,
        client_id=client_id,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _position_reference(**overrides) -> PositionReferenceEvidenceV2:
    base = dict(
        payload_version=2,
        local_recognition_id="local-position-1",
        raw_code="POS-1",
        normalized_code="POS-1",
        remote_position_id=None,
        remote_position_label_id=None,
        source="LOCAL_CODE_SCAN",
        profile_id=None,
        profile_version=None,
        client_supplier_id=None,
        signature=PositionSignatureEvidenceV2(
            present=False,
            verification="MISSING",
        ),
        captured_at=datetime(2026, 7, 24, 11, 59, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return PositionReferenceEvidenceV2(**base)


class _CanonicalValidatorStub:
    def __init__(self) -> None:
        self.commands = []

    def validate(self, command):
        self.commands.append(command)
        return CanonicalPositionValidationResult(
            status=CanonicalPositionValidationStatus.VALID_EXISTING,
            recognition=CanonicalPositionRecognition(
                raw_code="POS-1",
                normalized_code="POS-1",
                source=PositionRecognitionSource.MOBILE,
            ),
            existing_position_label_id="server-label-1",
        )


def _cmd(**overrides) -> UpsertPreliminaryDetectionCommand:
    base = dict(
        inventory_id="inv-1",
        aisle_id="aisle-1",
        draft_id="draft-1",
        schema_version="1",
        capture_session_id="sess-1",
        capture_photo_id="photo-1",
        client_file_id="cf-1",
        asset_id="asset-1",
        processing_mode="CODE_SCAN",
        status="RESOLVED",
        internal_code="ABC123",
        quantity=10,
        quantity_status="PRESENT",
        detected_format="PIPE",
        detected_symbology="QR_CODE",
        candidate_count=1,
        parser_version="1.1.0",
        detector_version="mlkit-barcode-1.0.0",
        prepared_asset_sha256="sha256:" + ("a" * 64),
        payload_hash="sha256:" + ("b" * 64),
        processing_ms=120,
        detected_at=datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return UpsertPreliminaryDetectionCommand(**base)


def _uc(
    *,
    enabled: bool = True,
    aisle: Aisle | None = None,
    asset: SourceAsset | None = None,
    prelim: MemoryMobilePreliminaryDetectionRepository | None = None,
    inventory: Inventory | None = None,
    canonical_validator=None,
) -> tuple[UpsertPreliminaryDetectionUseCase, MemoryMobilePreliminaryDetectionRepository]:
    inventory_repo = MemoryInventoryRepository()
    aisle_repo = MemoryAisleRepository()
    asset_repo = MemorySourceAssetRepository()
    repo = prelim or MemoryMobilePreliminaryDetectionRepository()
    inventory_repo.save(inventory or _inventory())
    aisle_repo.save(aisle or _aisle())
    asset_repo.save(asset or _asset())
    return (
        UpsertPreliminaryDetectionUseCase(
            aisle_repo=aisle_repo,
            asset_repo=asset_repo,
            preliminary_repo=repo,
            clock=_FixedClock(),
            enabled=enabled,
            inventory_repo=inventory_repo,
            canonical_position_validator=canonical_validator,
        ),
        repo,
    )


def test_disabled_raises():
    uc, _ = _uc(enabled=False)
    with pytest.raises(PreliminaryDetectionIngestDisabledError):
        uc.execute(_cmd())


def test_create_validated():
    uc, _ = _uc()
    result = uc.execute(_cmd())
    assert result.status == "VALIDATED"
    assert result.server_preliminary_id
    assert result.duplicate is False
    assert result.requested_draft_id == "draft-1"
    assert result.draft_id == "draft-1"


def test_idempotent_repeat():
    uc, _ = _uc()
    first = uc.execute(_cmd())
    second = uc.execute(_cmd())
    assert second.duplicate is True
    assert second.server_preliminary_id == first.server_preliminary_id


def test_idempotency_content_conflict():
    uc, _ = _uc()
    uc.execute(_cmd())
    result = uc.execute(_cmd(internal_code="OTHER"))
    assert result.status == "CONFLICT"
    assert result.error_code == PRELIMINARY_IDEMPOTENCY_CONFLICT


def test_secondary_key_same_content_is_duplicate():
    uc, _ = _uc()
    first = uc.execute(_cmd(draft_id="draft-a"))
    second = uc.execute(_cmd(draft_id="draft-b"))
    assert second.duplicate is True
    assert second.draft_id == "draft-a"
    assert second.requested_draft_id == "draft-b"
    assert second.server_preliminary_id == first.server_preliminary_id


def test_secondary_key_divergent_content_is_conflict():
    uc, _ = _uc()
    uc.execute(_cmd(draft_id="draft-a", internal_code="CODE1"))
    result = uc.execute(_cmd(draft_id="draft-b", internal_code="CODE2"))
    assert result.status == "CONFLICT"
    assert result.error_code == PRELIMINARY_IDEMPOTENCY_CONFLICT
    assert result.draft_id == "draft-a"
    assert result.requested_draft_id == "draft-b"


def test_unique_violation_race_returns_duplicate():
    class RaceRepo(MemoryMobilePreliminaryDetectionRepository):
        def __init__(self) -> None:
            super().__init__()
            self._first_insert = True

        def insert(self, row: MobilePreliminaryDetection) -> MobilePreliminaryDetection:
            if self._first_insert:
                self._first_insert = False
                # Simulate concurrent winner already present
                super().insert(row)
                raise PreliminaryUniqueViolationError("draft_id")
            return super().insert(row)

    uc, _ = _uc(prelim=RaceRepo())
    result = uc.execute(_cmd())
    assert result.duplicate is True
    assert result.status == "VALIDATED"


def test_canonicalizer_normalizes_case_and_sha():
    canon = PreliminaryDetectionContentCanonicalizer()
    a = canon.from_command_like(
        _cmd(status="resolved", prepared_asset_sha256="SHA256:" + ("A" * 64))
    )
    b = canon.from_command_like(
        _cmd(status="RESOLVED", prepared_asset_sha256="sha256:" + ("a" * 64))
    )
    assert canon.same_for_draft_id(a, b)


def test_asset_missing_pending():
    aisle_repo = MemoryAisleRepository()
    aisle_repo.save(_aisle())
    uc = UpsertPreliminaryDetectionUseCase(
        aisle_repo=aisle_repo,
        asset_repo=MemorySourceAssetRepository(),
        preliminary_repo=MemoryMobilePreliminaryDetectionRepository(),
        clock=_FixedClock(),
        enabled=True,
    )
    result = uc.execute(_cmd())
    assert result.status == "PENDING_ASSET"


def test_purge_expired():
    uc, repo = _uc()
    uc.execute(_cmd())
    # Force expire
    row = repo.get_by_draft_id("draft-1")
    assert row is not None
    expired = MobilePreliminaryDetection(
        **{**row.__dict__, "expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}
    )
    repo._by_draft[row.draft_id] = expired
    repo._by_idem[
        (row.client_file_id, row.detector_version, row.parser_version, row.prepared_asset_sha256)
    ] = expired
    assert uc.purge_expired() == 1
    assert repo.get_by_draft_id("draft-1") is None


def test_v2_position_is_validated_with_mobile_source_and_server_client_scope():
    validator = _CanonicalValidatorStub()
    uc, repo = _uc(canonical_validator=validator)

    result = uc.execute(_cmd(schema_version="2", position_reference=_position_reference()))

    assert result.position_result is not None
    assert result.position_result.status == "ACCEPTED_EXISTING"
    assert result.position_result.remote_position_label_id == "server-label-1"
    assert result.position_result.reconciliation_revision == 1
    command = validator.commands[0]
    assert command.source is PositionRecognitionSource.MOBILE
    assert command.context.client_id == "client-server"
    saved = repo.get_by_draft_id("draft-1")
    assert saved is not None
    assert saved.position_result_status == "ACCEPTED_EXISTING"
    assert saved.position_local_recognition_id == "local-position-1"


def test_v1_retry_as_v2_is_an_idempotency_conflict():
    validator = _CanonicalValidatorStub()
    uc, _ = _uc(canonical_validator=validator)
    uc.execute(_cmd())

    result = uc.execute(_cmd(schema_version="2", position_reference=_position_reference()))

    assert result.status == "CONFLICT"
    assert result.error_code == PRELIMINARY_IDEMPOTENCY_CONFLICT
    assert validator.commands == []


def test_v2_position_evidence_participates_in_idempotency_content():
    validator = _CanonicalValidatorStub()
    uc, _ = _uc(canonical_validator=validator)
    uc.execute(_cmd(schema_version="2", position_reference=_position_reference()))

    result = uc.execute(
        _cmd(
            schema_version="2",
            position_reference=_position_reference(local_recognition_id="different"),
        )
    )

    assert result.status == "CONFLICT"


def test_v2_exact_retry_returns_persisted_authoritative_result():
    validator = _CanonicalValidatorStub()
    uc, _ = _uc(canonical_validator=validator)
    command = _cmd(schema_version="2", position_reference=_position_reference())
    uc.execute(command)

    result = uc.execute(command)

    assert result.duplicate is True
    assert result.position_result is not None
    assert result.position_result.status == "ACCEPTED_EXISTING"
    assert len(validator.commands) == 1


def test_v2_never_uses_client_supplier_claim_as_tenant_authority():
    validator = _CanonicalValidatorStub()
    uc, _ = _uc(canonical_validator=validator)

    result = uc.execute(
        _cmd(
            schema_version="2",
            position_reference=_position_reference(client_supplier_id="foreign-supplier"),
        )
    )

    assert result.position_result is not None
    assert result.position_result.status == "REJECTED_SCOPE"
    assert result.position_result.error_code == "POSITION_SUPPLIER_SCOPE_MISMATCH"


def test_v2_remote_position_claim_is_evidence_not_authoritative_output():
    validator = _CanonicalValidatorStub()
    uc, repo = _uc(canonical_validator=validator)

    result = uc.execute(
        _cmd(
            schema_version="2",
            position_reference=_position_reference(remote_position_id="client-claimed-position"),
        )
    )

    assert result.position_result is not None
    assert result.position_result.status == "ACCEPTED_EXISTING"
    assert result.position_result.remote_position_id is None
    saved = repo.get_by_draft_id("draft-1")
    assert saved is not None
    assert saved.position_claimed_remote_id == "client-claimed-position"
    assert saved.position_remote_id is None


def test_v2_retryable_validation_is_not_cached_as_final_evidence():
    class RetryableValidator:
        calls = 0

        def validate(self, command):
            self.calls += 1
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                error_code="POSITION_RESOLUTION_UNAVAILABLE",
            )

    validator = RetryableValidator()
    uc, repo = _uc(canonical_validator=validator)
    command = _cmd(schema_version="2", position_reference=_position_reference())

    first = uc.execute(command)
    second = uc.execute(command)

    assert first.position_result is not None
    assert first.position_result.status == "RETRYABLE_ERROR"
    assert first.server_preliminary_id == ""
    assert second.position_result is not None
    assert validator.calls == 2
    assert repo.get_by_draft_id(command.draft_id) is None
