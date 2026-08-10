"""Unit tests for client-scoped positioning labels (no inventory/aisle)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    ClientPositionLabelAccessDeniedError,
    ClientPositionLabelConflictError,
    ClientPositionLabelNotFoundError,
    IdempotencyKeyReusedError,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.application.use_cases.client_position_labels.manage import (
    CreateClientPositionLabelCommand,
    CreateClientPositionLabelUseCase,
    CreateClientPositionMarkerSetCommand,
    CreateClientPositionMarkerSetUseCase,
    GetClientPositionLabelCommand,
    GetClientPositionLabelUseCase,
    InvalidateClientPositionLabelCommand,
    InvalidateClientPositionLabelUseCase,
    ListClientPositionLabelsCommand,
    ListClientPositionLabelsUseCase,
)
from src.domain.aisle_location.label_entities import POSITIONING_LABEL_PAYLOAD_VERSION_V2
from src.domain.aisle_location.payload import validate_positioning_payload
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_position_label.entities import ClientPositionLabelStatus
from src.infrastructure.repositories.memory_client_position_label_repository import (
    MemoryClientPositionLabelRepository,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


class _MemoryClientRepo:
    def __init__(self, clients: list[Client]) -> None:
        self._by_id = {c.id: c for c in clients}

    def get_by_id(self, client_id: str) -> Client | None:
        return self._by_id.get(client_id)


def _client(client_id: str = "client-a") -> Client:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Client(
        id=client_id,
        name="Acme",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _platform() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="admin-1", is_platform=True, client_id=None, roles=frozenset({"admin"})
    )


def _company(client_id: str) -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="user-1",
        is_platform=False,
        client_id=client_id,
        roles=frozenset({"operator"}),
    )


def _signing(*, required: bool = False, secret: str | None = "test-secret-16chars") -> PositioningLabelSigningService:
    return PositioningLabelSigningService(
        PositioningLabelSigningConfig(secret=secret, key_version=1, required=required)
    )


def _create_uc(
    label_repo: MemoryClientPositionLabelRepository,
    client_repo: _MemoryClientRepo,
    *,
    signing: PositioningLabelSigningService | None = None,
) -> CreateClientPositionLabelUseCase:
    return CreateClientPositionLabelUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=_FixedClock(),
        signing=signing if signing is not None else _signing(),
    )


def test_create_without_inventory_or_aisle() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client()])
    uc = _create_uc(label_repo, client_repo)
    label = uc.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a",
            name="A-01-03",
            description="Rack A, nivel 3",
            principal=_platform(),
        )
    )
    assert label.client_id == "client-a"
    assert label.name == "A-01-03"
    assert label.public_identifier.startswith("pos_")
    assert label.status == ClientPositionLabelStatus.ACTIVE
    validate_positioning_payload(label.canonical_payload)
    assert "inventory_id" not in label.canonical_payload
    assert "aisle_id" not in label.canonical_payload
    assert label.canonical_payload["type"] == "DINAMIC_POSITION"
    assert label.canonical_payload["label_id"] == label.public_identifier
    assert label.signature_status.value == "SIGNED"


def test_create_name_required() -> None:
    uc = _create_uc(MemoryClientPositionLabelRepository(), _MemoryClientRepo([_client()]))
    with pytest.raises(ClientPositionLabelConflictError) as exc:
        uc.execute(
            CreateClientPositionLabelCommand(
                client_id="client-a", name="  ", principal=_platform()
            )
        )
    assert exc.value.code == "POSITION_LABEL_NAME_REQUIRED"


def test_list_by_client_and_cross_tenant_denied() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client("client-a"), _client("client-b")])
    create = _create_uc(label_repo, client_repo)
    create.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a", name="Zona A", principal=_platform()
        )
    )
    list_uc = ListClientPositionLabelsUseCase(label_repo=label_repo, client_repo=client_repo)
    items, total = list_uc.execute(
        ListClientPositionLabelsCommand(
            client_id="client-a", principal=_company("client-a")
        )
    )
    assert total == 1
    assert items[0].name == "Zona A"
    with pytest.raises(ClientPositionLabelAccessDeniedError):
        list_uc.execute(
            ListClientPositionLabelsCommand(
                client_id="client-a", principal=_company("client-b")
            )
        )


def test_idempotency_same_and_conflict() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client()])
    uc = _create_uc(label_repo, client_repo)
    first = uc.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a",
            name="A-01",
            principal=_platform(),
            idempotency_key="idem-1",
        )
    )
    second = uc.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a",
            name="A-01",
            principal=_platform(),
            idempotency_key="idem-1",
        )
    )
    assert first.id == second.id
    with pytest.raises(IdempotencyKeyReusedError):
        uc.execute(
            CreateClientPositionLabelCommand(
                client_id="client-a",
                name="A-02",
                principal=_platform(),
                idempotency_key="idem-1",
            )
        )


def test_invalidate_and_get_mismatch() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client("client-a"), _client("client-b")])
    create = _create_uc(label_repo, client_repo)
    label = create.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a", name="Entrada", principal=_platform()
        )
    )
    inv = InvalidateClientPositionLabelUseCase(
        label_repo=label_repo, client_repo=client_repo, clock=_FixedClock()
    )
    invalidated = inv.execute(
        InvalidateClientPositionLabelCommand(
            client_id="client-a",
            label_id=label.id,
            principal=_platform(),
            reason="damaged",
        )
    )
    assert invalidated.status == ClientPositionLabelStatus.INVALIDATED
    get_uc = GetClientPositionLabelUseCase(label_repo=label_repo, client_repo=client_repo)
    with pytest.raises(ClientPositionLabelNotFoundError):
        get_uc.execute(
            GetClientPositionLabelCommand(
                client_id="client-b",
                label_id=label.id,
                principal=_platform(),
            )
        )


def test_payload_has_no_inventory_fields() -> None:
    """Regression: client labels must not encode inventory/aisle ownership in QR."""
    label_repo = MemoryClientPositionLabelRepository()
    create = _create_uc(label_repo, _MemoryClientRepo([_client()]))
    label = create.execute(
        CreateClientPositionLabelCommand(
            client_id="client-a",
            name=f"loc-{uuid4().hex[:6]}",
            principal=_platform(),
        )
    )
    forbidden = {"inventory_id", "aisle_id", "job_id", "session_id", "deposit_id"}
    assert forbidden.isdisjoint(label.canonical_payload.keys())


def test_marker_set_creates_padded_labels() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client()])
    uc = CreateClientPositionMarkerSetUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=_FixedClock(),
        signing=_signing(),
    )
    labels = uc.execute(
        CreateClientPositionMarkerSetCommand(
            client_id="client-a",
            pallet="P12",
            side="LEFT",
            level=3,
            marker_total=3,
            principal=_platform(),
        )
    )
    assert len(labels) == 3
    assert [lab.marker_index for lab in labels] == [1, 2, 3]
    assert all(lab.marker_total == 3 for lab in labels)
    assert all(lab.pallet == "P12" for lab in labels)
    assert all(lab.side == "LEFT" for lab in labels)
    assert all(lab.level == 3 for lab in labels)
    assert all(lab.payload_version == POSITIONING_LABEL_PAYLOAD_VERSION_V2 for lab in labels)
    assert labels[0].name == "P12 LEFT N3 01/03"
    assert labels[1].name == "P12 LEFT N3 02/03"
    assert labels[2].name == "P12 LEFT N3 03/03"
    public_ids = {lab.public_identifier for lab in labels}
    assert len(public_ids) == 3
    for lab in labels:
        validate_positioning_payload(lab.canonical_payload)
        assert lab.canonical_payload["version"] == 2
        assert lab.canonical_payload["marker_index"] == lab.marker_index


def test_marker_set_atomic_rollback_on_save_many_failure() -> None:
    class _FailingAtomic(MemoryClientPositionLabelRepository):
        def save_many(self, labels):  # type: ignore[no-untyped-def]
            inserted: list[str] = []
            try:
                for i, label in enumerate(labels):
                    if i == 1:
                        raise RuntimeError("fail mid-way")
                    self._labels[label.id] = label
                    inserted.append(label.id)
                return labels
            except Exception:
                for lid in inserted:
                    self._labels.pop(lid, None)
                raise

    repo = _FailingAtomic()
    uc = CreateClientPositionMarkerSetUseCase(
        label_repo=repo,
        client_repo=_MemoryClientRepo([_client()]),
        clock=_FixedClock(),
        signing=_signing(),
    )
    with pytest.raises(RuntimeError, match="fail mid-way"):
        uc.execute(
            CreateClientPositionMarkerSetCommand(
                client_id="client-a",
                pallet="P99",
                side="RIGHT",
                level=1,
                marker_total=3,
                principal=_platform(),
            )
        )
    assert repo.list_by_client("client-a", limit=100) == []


def test_memory_save_many_rolls_back_on_active_marker_conflict() -> None:
    from src.domain.client_position_label.entities import (
        ClientPositionLabel,
        ClientPositionLabelSignatureStatus,
        ClientPositionLabelStatus,
    )

    repo = MemoryClientPositionLabelRepository()
    now = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)

    def _label(*, lid: str, name: str, marker_index: int) -> ClientPositionLabel:
        return ClientPositionLabel(
            id=lid,
            client_id="client-a",
            public_identifier=f"pos_{lid}",
            name=name,
            normalized_name=name.upper(),
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=2,
            canonical_payload={"type": "DINAMIC_POSITION", "version": 2, "label_id": f"pos_{lid}"},
            created_at=now,
            updated_at=now,
            signature_status=ClientPositionLabelSignatureStatus.UNSIGNED,
            pallet="P1",
            side="LEFT",
            level=1,
            marker_index=marker_index,
            marker_total=2,
        )

    first = _label(lid="a", name="A", marker_index=1)
    conflict = _label(lid="b", name="B", marker_index=1)
    with pytest.raises(ClientPositionLabelConflictError) as exc:
        repo.save_many([first, conflict])
    assert exc.value.code == "POSITION_LABEL_MARKER_ACTIVE_EXISTS"
    assert repo.get_by_id("a") is None
    assert repo.get_by_id("b") is None


def test_marker_set_idempotent_retry() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client()])
    uc = CreateClientPositionMarkerSetUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=_FixedClock(),
        signing=_signing(),
    )
    first = uc.execute(
        CreateClientPositionMarkerSetCommand(
            client_id="client-a",
            pallet="P12",
            side="LEFT",
            level=3,
            marker_total=2,
            principal=_platform(),
            idempotency_key="marker-set-1",
        )
    )
    second = uc.execute(
        CreateClientPositionMarkerSetCommand(
            client_id="client-a",
            pallet="P12",
            side="LEFT",
            level=3,
            marker_total=2,
            principal=_platform(),
            idempotency_key="marker-set-1",
        )
    )
    assert [lab.id for lab in first] == [lab.id for lab in second]
    assert first[0].idempotency_key == "marker-set-1"
    assert first[1].idempotency_key is None
    with pytest.raises(IdempotencyKeyReusedError):
        uc.execute(
            CreateClientPositionMarkerSetCommand(
                client_id="client-a",
                pallet="P12",
                side="LEFT",
                level=4,
                marker_total=2,
                principal=_platform(),
                idempotency_key="marker-set-1",
            )
        )


def test_marker_set_active_uniqueness_conflict() -> None:
    label_repo = MemoryClientPositionLabelRepository()
    client_repo = _MemoryClientRepo([_client()])
    uc = CreateClientPositionMarkerSetUseCase(
        label_repo=label_repo,
        client_repo=client_repo,
        clock=_FixedClock(),
        signing=_signing(),
    )
    uc.execute(
        CreateClientPositionMarkerSetCommand(
            client_id="client-a",
            pallet="P12",
            side="LEFT",
            level=3,
            marker_total=2,
            principal=_platform(),
        )
    )
    with pytest.raises(ClientPositionLabelConflictError) as exc:
        uc.execute(
            CreateClientPositionMarkerSetCommand(
                client_id="client-a",
                pallet="P12",
                side="LEFT",
                level=3,
                marker_total=2,
                principal=_platform(),
            )
        )
    assert exc.value.code in {
        "POSITION_LABEL_MARKER_ACTIVE_EXISTS",
        "POSITION_LABEL_NAME_CONFLICT",
    }
