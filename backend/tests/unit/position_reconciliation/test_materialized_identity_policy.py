from datetime import datetime, timezone

from src.application.ports.materialized_position_identity_reader import (
    TrustedMaterializedPositionIdentity,
)
from src.application.services.position_reconciliation.fingerprint import (
    build_fingerprint_from_frames,
)
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
    PositionMaterializationAssociationStatus,
    PositionMaterializationStatus,
)
from src.domain.position_reconciliation.entities import (
    OrderedImageFrame,
    PositionDetectionRef,
)
from src.infrastructure.persistence.memory_materialized_position_identity_reader import (
    MemoryMaterializedPositionIdentityReader,
)
from src.infrastructure.persistence.memory_position_materialization_unit_of_work import (
    MemoryMaterializationAisle,
    MemoryMaterializationInventory,
    MemoryMaterializationRequest,
    MemoryMaterializedLocation,
    MemoryPositionMaterializationUnitOfWork,
)


def test_memory_reader_fails_closed_on_scope_and_association_state() -> None:
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    unit_of_work = MemoryPositionMaterializationUnitOfWork(
        inventories=[MemoryMaterializationInventory("inventory-1", "client-1")],
        aisles=[MemoryMaterializationAisle("aisle-1", "inventory-1")],
        locations=[
            MemoryMaterializedLocation(
                id="location-1",
                public_identifier="A04-R-02",
                client_id="client-1",
                aisle_id="aisle-1",
                code="A04-R-02",
                normalized_code="A04-R-02",
                status="ACTIVE",
                created_by="test",
                created_at=now,
                updated_at=now,
            )
        ],
    )
    unit_of_work.requests[("client-1", "key-1")] = MemoryMaterializationRequest(
        id="request-1",
        client_id="client-1",
        inventory_id="inventory-1",
        aisle_id="aisle-1",
        location_id="location-1",
        idempotency_key="key-1",
        request_hash="hash",
        normalized_code="A04-R-02",
        source="VISION",
        actor="test",
        result=PositionMaterializationStatus.MATERIALIZED,
        created_at=now,
        association_status=PositionMaterializationAssociationStatus.ASSOCIATED,
        associated_at=now,
    )
    unit_of_work.association_receipt_repository.save(
        PositionMaterializationAssociationReceipt(
            request_id="request-1",
            target_type="IMAGE_RESULT",
            target_id="evidence-1",
            created_at=now,
            source_detection_id="d1",
        )
    )
    reader = MemoryMaterializedPositionIdentityReader(unit_of_work)
    identity = TrustedMaterializedPositionIdentity("d1", "request-1", "location-1")
    assert reader.read_by_detection_ids(
        ["d1"], client_id="client-1", inventory_id="inventory-1", aisle_id="aisle-1"
    ) == {"d1": identity}
    assert reader.read_by_detection_ids(
        ["d1"], client_id="other", inventory_id="inventory-1", aisle_id="aisle-1"
    ) == {}


def test_materialization_association_changes_reconciliation_fingerprint() -> None:
    def fingerprint(location_id: str | None) -> str:
        detection = PositionDetectionRef(
            id="d1",
            client_id="client-1",
            detection_status="VALID",
            signature_status="SKIPPED",
            aisle_location_id=location_id,
            position_name_snapshot="A04-R-02",
        )
        return build_fingerprint_from_frames(
            [
                OrderedImageFrame(
                    source_asset_id="asset-1",
                    ordered_capture_session_id=None,
                    sequence_number=0,
                    position_detections=(detection,),
                )
            ],
            sequence_version=1,
        )

    assert fingerprint(None) != fingerprint("location-1")
