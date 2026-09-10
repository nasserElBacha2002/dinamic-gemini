"""Thread-safe in-memory position materialization UOW."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from src.application.dto.position_materialization import (
    POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
    MaterializePositionCommand,
)
from src.application.ports.aisle_location_repository import AisleLocationRepository
from src.application.ports.materialized_position_identity_reader import (
    TrustedMaterializedPositionIdentity,
)
from src.application.ports.position_materialization_association_receipt_repository import (
    PositionMaterializationAssociationReceiptRepository,
)
from src.domain.aisle_location.entities import AisleLocation, AisleLocationStatus
from src.domain.inventory.write_policy import writable_status_values
from src.domain.position_materialization.entities import (
    MaterializePositionResult,
    PositionMaterializationAssociationClaim,
    PositionMaterializationAssociationEvidence,
    PositionMaterializationAssociationReceipt,
    PositionMaterializationAssociationStatus,
    PositionMaterializationEvidenceStatus,
    PositionMaterializationStatus,
)
from src.domain.position_materialization.errors import (
    PositionMaterializationConflictError,
    PositionMaterializationInvariantError,
    PositionMaterializationInventoryStateError,
    PositionMaterializationRetryableError,
    PositionMaterializationScopeError,
)
from src.infrastructure.persistence.memory_position_materialization_association_receipt_repository import (
    MemoryPositionMaterializationAssociationReceiptRepository,
)

_WRITABLE_INVENTORY_STATUSES = writable_status_values()


@dataclass(frozen=True)
class MemoryMaterializationInventory:
    id: str
    client_id: str
    status: str = "draft"
    deleted: bool = False


@dataclass(frozen=True)
class MemoryMaterializationAisle:
    id: str
    inventory_id: str
    client_supplier_id: str | None = None
    is_active: bool = True


@dataclass
class MemoryMaterializedLocation:
    id: str
    public_identifier: str
    client_id: str
    aisle_id: str
    code: str
    normalized_code: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    creation_source: str = "AUTO"
    recognition_source: str | None = None
    client_supplier_id: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    raw_recognition_code: str | None = None
    pallet: str | None = None
    side: str | None = None
    level: int | None = None
    marker_index: int | None = None
    marker_total: int | None = None
    source_capture_id: str | None = None
    auto_materialized_at: datetime | None = None


@dataclass(frozen=True)
class MemoryMaterializationRequest:
    id: str
    client_id: str
    inventory_id: str
    aisle_id: str
    location_id: str
    idempotency_key: str
    request_hash: str
    normalized_code: str
    source: str
    actor: str
    result: PositionMaterializationStatus
    created_at: datetime
    fingerprint_version: int = POSITION_MATERIALIZATION_FINGERPRINT_VERSION
    association_status: PositionMaterializationAssociationStatus = (
        PositionMaterializationAssociationStatus.PENDING
    )
    associated_at: datetime | None = None
    association_error_code: str | None = None
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None


def _conflict(message: str, code: str) -> PositionMaterializationConflictError:
    return PositionMaterializationConflictError(message, code=code)


class MemoryPositionMaterializationUnitOfWork:
    def __init__(
        self,
        *,
        inventories: list[MemoryMaterializationInventory] | None = None,
        aisles: list[MemoryMaterializationAisle] | None = None,
        locations: list[MemoryMaterializedLocation] | None = None,
        location_repository: AisleLocationRepository | None = None,
        failure_hook: Callable[[], None] | None = None,
        repository_refresh_page_size: int = 500,
    ) -> None:
        if repository_refresh_page_size < 1:
            raise ValueError("repository_refresh_page_size must be positive")
        self.inventories = {row.id: row for row in inventories or []}
        self.aisles = {row.id: row for row in aisles or []}
        self.locations = {row.id: row for row in locations or []}
        self.requests: dict[tuple[str, str], MemoryMaterializationRequest] = {}
        self.receipts: dict[str, PositionMaterializationAssociationReceipt] = {}
        self.preliminary_request_ids: set[str] = set()
        self._location_repository = location_repository
        self._failure_hook = failure_hook
        self._repository_refresh_page_size = repository_refresh_page_size
        self._pending_local_location_ids: set[str] = set()
        self._lock = threading.RLock()
        self._receipt_repository = MemoryPositionMaterializationAssociationReceiptRepository(
            store=self.receipts,
            lock=self._lock,
        )

    @property
    def association_receipt_repository(
        self,
    ) -> PositionMaterializationAssociationReceiptRepository:
        return self._receipt_repository

    def read_materialized_identities(
        self,
        detection_ids: tuple[str, ...],
        *,
        client_id: str,
        inventory_id: str,
        aisle_id: str,
    ) -> dict[str, TrustedMaterializedPositionIdentity]:
        requested = set(detection_ids)
        identities: dict[str, TrustedMaterializedPositionIdentity] = {}
        with self._lock:
            requests_by_id = {row.id: row for row in self.requests.values()}
            for receipt in self.receipts.values():
                detection_id = receipt.source_detection_id
                if detection_id is None or detection_id not in requested:
                    continue
                request = requests_by_id.get(receipt.request_id)
                if (
                    request is None
                    or receipt.target_type != "IMAGE_RESULT"
                    or request.association_status
                    is not PositionMaterializationAssociationStatus.ASSOCIATED
                    or request.client_id != client_id
                    or request.inventory_id != inventory_id
                    or request.aisle_id != aisle_id
                ):
                    continue
                location = self.locations.get(request.location_id)
                aisle = self.aisles.get(aisle_id)
                if (
                    location is None
                    or location.client_id != client_id
                    or location.aisle_id != aisle_id
                    or location.status != AisleLocationStatus.ACTIVE.value
                    or aisle is None
                    or aisle.inventory_id != inventory_id
                    or not aisle.is_active
                ):
                    continue
                identities[detection_id] = TrustedMaterializedPositionIdentity(
                    detection_id=detection_id,
                    request_id=request.id,
                    aisle_location_id=location.id,
                )
        return identities

    def add_inventory(self, inventory: MemoryMaterializationInventory) -> None:
        with self._lock:
            self.inventories[inventory.id] = inventory

    def add_aisle(self, aisle: MemoryMaterializationAisle) -> None:
        with self._lock:
            self.aisles[aisle.id] = aisle

    def add_location(self, location: MemoryMaterializedLocation) -> None:
        with self._lock:
            self.locations[location.id] = location

    def lookup_replay(
        self,
        *,
        client_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> MaterializePositionResult | None:
        with self._lock:
            replay = self.requests.get((client_id, idempotency_key))
            if replay is None:
                return None
            self._validate_fingerprint_version(replay)
            if replay.request_hash != request_hash:
                raise _conflict(
                    "Idempotency key was used with a different payload",
                    "IDEMPOTENCY_KEY_CONFLICT",
                )
            location = self.locations.get(replay.location_id)
            if location is None:
                raise RuntimeError("Materialization ledger references a missing location")
            return MaterializePositionResult(
                status=replay.result,
                idempotent_replay=True,
                location_id=location.id,
                public_identifier=location.public_identifier,
                request_id=replay.id,
            )

    def materialize(
        self,
        command: MaterializePositionCommand,
        *,
        request_hash: str,
        now: datetime,
    ) -> MaterializePositionResult:
        client_id = command.principal.client_id
        if client_id is None:
            raise PositionMaterializationScopeError(
                "Tenant principal required",
                code="PRINCIPAL_CLIENT_REQUIRED",
            )
        with self._lock:
            self._load_repository_locations(command.aisle_id)
            locations_before = copy.deepcopy(self.locations)
            requests_before = dict(self.requests)
            try:
                return self._materialize_locked(command, client_id, request_hash, now)
            except Exception:
                self.locations.clear()
                self.locations.update(locations_before)
                self.requests.clear()
                self.requests.update(requests_before)
                raise

    def _materialize_locked(
        self,
        command: MaterializePositionCommand,
        client_id: str,
        request_hash: str,
        now: datetime,
    ) -> MaterializePositionResult:
        replay = self.requests.get((client_id, command.idempotency_key))
        if replay is not None:
            self._validate_fingerprint_version(replay)
            if replay.request_hash != request_hash:
                raise _conflict(
                    "Idempotency key was used with a different payload",
                    "IDEMPOTENCY_KEY_CONFLICT",
                )
            location = self.locations[replay.location_id]
            return MaterializePositionResult(
                status=replay.result,
                idempotent_replay=True,
                location_id=location.id,
                public_identifier=location.public_identifier,
                request_id=replay.id,
            )

        inventory = self.inventories.get(command.inventory_id)
        if inventory is None or inventory.client_id != client_id or inventory.deleted:
            raise PositionMaterializationScopeError(
                "Inventory is outside the principal scope",
                code="INVENTORY_SCOPE_MISMATCH",
            )
        aisle = self.aisles.get(command.aisle_id)
        if aisle is None or aisle.inventory_id != inventory.id:
            raise PositionMaterializationScopeError(
                "Aisle is outside the inventory scope",
                code="AISLE_SCOPE_MISMATCH",
            )
        if not aisle.is_active:
            raise PositionMaterializationScopeError(
                "Aisle is inactive",
                code="AISLE_INACTIVE",
            )
        if aisle.client_supplier_id != command.recognition.client_supplier_id:
            raise PositionMaterializationScopeError(
                "Recognition supplier does not match aisle supplier",
                code="SUPPLIER_SCOPE_MISMATCH",
            )
        if inventory.status.lower() not in _WRITABLE_INVENTORY_STATUSES:
            raise PositionMaterializationInventoryStateError(
                "Inventory does not accept new positions",
                code="INVENTORY_NOT_WRITABLE",
            )

        matches = [
            row
            for row in self.locations.values()
            if row.client_id == client_id
            and row.aisle_id == aisle.id
            and row.normalized_code == command.recognition.normalized_code
        ]
        active = next((row for row in matches if row.status == "ACTIVE"), None)
        if active is None and matches:
            raise _conflict(
                "An inactive location already owns this canonical identity",
                "INACTIVE_POSITION_IDENTITY",
            )

        if active is None:
            location_id = str(uuid.uuid4())
            active = MemoryMaterializedLocation(
                id=location_id,
                public_identifier=f"loc_{location_id.replace('-', '')}",
                client_id=client_id,
                aisle_id=aisle.id,
                code=command.recognition.normalized_code,
                normalized_code=command.recognition.normalized_code,
                status="ACTIVE",
                created_by=command.principal.actor_id,
                created_at=now,
                updated_at=now,
                recognition_source=command.recognition.source.value,
                client_supplier_id=command.recognition.client_supplier_id,
                profile_id=command.recognition.profile_id,
                profile_version=command.recognition.profile_version,
                raw_recognition_code=command.recognition.raw_code,
                pallet=command.recognition.pallet,
                side=command.recognition.side,
                level=command.recognition.level,
                marker_index=command.recognition.marker_index,
                marker_total=command.recognition.marker_total,
                source_capture_id=command.capture_id,
                auto_materialized_at=now,
            )
            result_status = PositionMaterializationStatus.MATERIALIZED
        else:
            self._validate_compatible(active, command)
            result_status = PositionMaterializationStatus.REUSED

        if self._failure_hook is not None:
            try:
                self._failure_hook()
            except PositionMaterializationRetryableError:
                raise
            except OSError as exc:
                raise PositionMaterializationRetryableError(
                    "Injected persistence failure",
                    code="PERSISTENCE_FAILURE",
                ) from exc

        pending_local = result_status is PositionMaterializationStatus.MATERIALIZED
        if pending_local:
            self._pending_local_location_ids.add(active.id)
        try:
            if pending_local:
                self._persist_new_location(active)
                self.locations[active.id] = active

            request_id = str(uuid.uuid4())
            self.requests[(client_id, command.idempotency_key)] = MemoryMaterializationRequest(
                id=request_id,
                client_id=client_id,
                inventory_id=inventory.id,
                aisle_id=aisle.id,
                location_id=active.id,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                normalized_code=command.recognition.normalized_code,
                source=command.recognition.source.value,
                actor=command.principal.actor_id,
                result=result_status,
                created_at=now,
                fingerprint_version=POSITION_MATERIALIZATION_FINGERPRINT_VERSION,
            )
        finally:
            if pending_local:
                self._pending_local_location_ids.discard(active.id)
        return MaterializePositionResult(
            status=result_status,
            idempotent_replay=False,
            location_id=active.id,
            public_identifier=active.public_identifier,
            request_id=request_id,
        )

    def _load_repository_locations(self, aisle_id: str) -> None:
        if self._location_repository is None:
            return
        repository_rows: list[AisleLocation] = []
        offset = 0
        while True:
            page = self._location_repository.list_by_aisle(
                aisle_id,
                limit=self._repository_refresh_page_size,
                offset=offset,
            )
            repository_rows.extend(page)
            if len(page) < self._repository_refresh_page_size:
                break
            offset += len(page)
        repository_ids = {location.id for location in repository_rows}
        for location in repository_rows:
            previous = self.locations.get(location.id)
            self.locations[location.id] = MemoryMaterializedLocation(
                id=location.id,
                public_identifier=location.public_identifier,
                client_id=location.client_id,
                aisle_id=location.aisle_id,
                code=location.code,
                normalized_code=location.normalized_code,
                status=location.status.value,
                created_by=location.created_by or "",
                created_at=location.created_at,
                updated_at=location.updated_at,
                creation_source=previous.creation_source if previous else "MANUAL",
                recognition_source=previous.recognition_source if previous else None,
                client_supplier_id=previous.client_supplier_id if previous else None,
                profile_id=previous.profile_id if previous else None,
                profile_version=previous.profile_version if previous else None,
                raw_recognition_code=previous.raw_recognition_code if previous else None,
                pallet=previous.pallet if previous else None,
                side=previous.side if previous else None,
                level=previous.level if previous else None,
                marker_index=previous.marker_index if previous else None,
                marker_total=previous.marker_total if previous else None,
                source_capture_id=previous.source_capture_id if previous else None,
                auto_materialized_at=previous.auto_materialized_at if previous else None,
            )
        stale_ids = [
            location_id
            for location_id, location in self.locations.items()
            if location.aisle_id == aisle_id
            and location_id not in repository_ids
            and location_id not in self._pending_local_location_ids
        ]
        for location_id in stale_ids:
            self.locations.pop(location_id, None)

    def complete_association(
        self,
        request_id: str,
        *,
        target: PositionMaterializationAssociationStatus,
        error_code: str | None,
        now: datetime,
    ) -> bool:
        with self._lock:
            item = next(
                (
                    (key, request)
                    for key, request in self.requests.items()
                    if request.id == request_id
                ),
                None,
            )
            if item is None:
                return False
            key, request = item
            if target is PositionMaterializationAssociationStatus.ASSOCIATED:
                if (
                    request.association_status
                    is PositionMaterializationAssociationStatus.ASSOCIATED
                ):
                    return True
                self.requests[key] = replace(
                    request,
                    association_status=target,
                    associated_at=now,
                    association_error_code=None,
                )
                return True
            if target is PositionMaterializationAssociationStatus.REQUIRES_REVIEW:
                if (
                    request.association_status
                    is PositionMaterializationAssociationStatus.REQUIRES_REVIEW
                ):
                    return True
                if (
                    request.association_status
                    is not PositionMaterializationAssociationStatus.PENDING
                ):
                    return False
                self.requests[key] = replace(
                    request,
                    association_status=target,
                    associated_at=None,
                    association_error_code=error_code,
                )
                return True
            raise ValueError(f"Unsupported association target: {target.value}")

    def get_association_status(
        self,
        request_id: str,
    ) -> PositionMaterializationAssociationStatus | None:
        with self._lock:
            request = next(
                (request for request in self.requests.values() if request.id == request_id),
                None,
            )
            return request.association_status if request is not None else None

    def claim_due_associations(
        self,
        *,
        owner: str,
        now: datetime,
        lease: timedelta,
        batch: int,
        max_attempts: int,
    ) -> list[PositionMaterializationAssociationClaim]:
        if not owner.strip() or batch < 1 or max_attempts < 1 or lease.total_seconds() <= 0:
            raise ValueError("Invalid association claim parameters")
        with self._lock:
            due = sorted(self.requests.items(), key=lambda item: (item[1].created_at, item[1].id))
            claims: list[PositionMaterializationAssociationClaim] = []
            for key, request in due:
                if len(claims) >= batch:
                    break
                if (
                    request.association_status
                    is not PositionMaterializationAssociationStatus.PENDING
                    or request.attempt_count >= max_attempts
                    or (request.next_retry_at is not None and request.next_retry_at > now)
                    or (
                        request.lease_owner is not None
                        and request.lease_expires_at is not None
                        and request.lease_expires_at > now
                    )
                ):
                    continue
                expires = now + lease
                self.requests[key] = replace(request, lease_owner=owner, lease_expires_at=expires)
                claims.append(
                    PositionMaterializationAssociationClaim(
                        request_id=request.id,
                        owner=owner,
                        attempt_count=request.attempt_count,
                        lease_expires_at=expires,
                    )
                )
            return claims

    def inspect_association_evidence(
        self, request_id: str
    ) -> PositionMaterializationAssociationEvidence:
        with self._lock:
            receipt = self.receipts.get(request_id)
            if receipt is not None:
                if receipt.target_type != "IMAGE_RESULT" or not receipt.target_id:
                    return PositionMaterializationAssociationEvidence(
                        status=PositionMaterializationEvidenceStatus.CONTRADICTION,
                        source=receipt.target_type,
                    )
                return PositionMaterializationAssociationEvidence(
                    status=PositionMaterializationEvidenceStatus.PRESENT,
                    source=receipt.target_type,
                    target_id=receipt.target_id,
                )
            if request_id in self.preliminary_request_ids:
                return PositionMaterializationAssociationEvidence(
                    status=PositionMaterializationEvidenceStatus.PRESENT,
                    source="MOBILE_PRELIMINARY_DETECTION",
                )
            return PositionMaterializationAssociationEvidence(
                status=PositionMaterializationEvidenceStatus.ABSENT
            )

    def complete_claimed(self, *, request_id: str, owner: str, now: datetime) -> bool:
        return self._finish_claimed(
            request_id, owner, now, PositionMaterializationAssociationStatus.ASSOCIATED, None, None
        )

    def reschedule_claimed(
        self,
        *,
        request_id: str,
        owner: str,
        now: datetime,
        next_retry_at: datetime,
        error_code: str,
    ) -> bool:
        return self._finish_claimed(
            request_id,
            owner,
            now,
            PositionMaterializationAssociationStatus.PENDING,
            next_retry_at,
            error_code,
        )

    def exhaust_claimed(
        self, *, request_id: str, owner: str, now: datetime, error_code: str
    ) -> bool:
        return self._finish_claimed(
            request_id,
            owner,
            now,
            PositionMaterializationAssociationStatus.EXHAUSTED,
            None,
            error_code,
        )

    def _finish_claimed(
        self,
        request_id: str,
        owner: str,
        now: datetime,
        status: PositionMaterializationAssociationStatus,
        next_retry_at: datetime | None,
        error_code: str | None,
    ) -> bool:
        with self._lock:
            item = next(
                ((key, row) for key, row in self.requests.items() if row.id == request_id),
                None,
            )
            if item is None:
                return False
            key, request = item
            if (
                request.association_status is not PositionMaterializationAssociationStatus.PENDING
                or request.lease_owner != owner
                or request.lease_expires_at is None
                or request.lease_expires_at <= now
            ):
                return False
            self.requests[key] = replace(
                request,
                association_status=status,
                associated_at=(
                    now if status is PositionMaterializationAssociationStatus.ASSOCIATED else None
                ),
                association_error_code=error_code,
                attempt_count=request.attempt_count + 1,
                last_attempt_at=now,
                next_retry_at=next_retry_at,
                lease_owner=None,
                lease_expires_at=None,
            )
            return True

    def release_expired_associations(self, *, now: datetime) -> int:
        released = 0
        with self._lock:
            for key, request in list(self.requests.items()):
                if (
                    request.association_status is PositionMaterializationAssociationStatus.PENDING
                    and request.lease_owner is not None
                    and request.lease_expires_at is not None
                    and request.lease_expires_at <= now
                ):
                    self.requests[key] = replace(request, lease_owner=None, lease_expires_at=None)
                    released += 1
        return released

    def _persist_new_location(self, location: MemoryMaterializedLocation) -> None:
        if self._location_repository is None:
            return
        try:
            self._location_repository.save(
                AisleLocation(
                    id=location.id,
                    public_identifier=location.public_identifier,
                    client_id=location.client_id,
                    aisle_id=location.aisle_id,
                    code=location.code,
                    normalized_code=location.normalized_code,
                    status=AisleLocationStatus.ACTIVE,
                    created_by=location.created_by,
                    created_at=location.created_at,
                    updated_at=location.updated_at,
                )
            )
        except OSError as exc:
            raise PositionMaterializationRetryableError(
                "Aisle location repository save failed",
                code="LOCATION_REPOSITORY_SAVE_FAILED",
            ) from exc

    @staticmethod
    def _validate_fingerprint_version(request: MemoryMaterializationRequest) -> None:
        if request.fingerprint_version != POSITION_MATERIALIZATION_FINGERPRINT_VERSION:
            raise PositionMaterializationInvariantError(
                "Stored materialization fingerprint version is unsupported",
                code="UNSUPPORTED_MATERIALIZATION_FINGERPRINT_VERSION",
            )

    @staticmethod
    def _validate_compatible(
        location: MemoryMaterializedLocation,
        command: MaterializePositionCommand,
    ) -> None:
        recognition = command.recognition
        fields = (
            ("client_supplier_id", location.client_supplier_id, recognition.client_supplier_id),
            ("profile_id", location.profile_id, recognition.profile_id),
            ("profile_version", location.profile_version, recognition.profile_version),
            ("pallet", location.pallet, recognition.pallet),
            ("side", location.side, recognition.side),
            ("level", location.level, recognition.level),
            ("marker_index", location.marker_index, recognition.marker_index),
            ("marker_total", location.marker_total, recognition.marker_total),
        )
        for field, persisted, requested in fields:
            if persisted is not None and requested is not None and persisted != requested:
                raise _conflict(
                    f"Existing location has contradictory {field}",
                    f"POSITION_{field.upper()}_CONFLICT",
                )
