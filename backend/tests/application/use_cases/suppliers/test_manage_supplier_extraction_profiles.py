"""Use-case tests for supplier extraction profile versioning (memory)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.errors import SupplierExtractionProfileInvalidConfigurationError
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ActivateSupplierExtractionProfileVersionCommand,
    ActivateSupplierExtractionProfileVersionUseCase,
    CreateSupplierExtractionProfileVersionCommand,
    CreateSupplierExtractionProfileVersionUseCase,
    ListSupplierExtractionProfilesCommand,
    ListSupplierExtractionProfilesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    default_extraction_configuration,
)
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed_client_supplier():
    client_id = str(uuid4())
    supplier_id = str(uuid4())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clients = MemoryClientRepository()
    suppliers = MemoryClientSupplierRepository()
    clients.save(
        Client(
            id=client_id,
            name="Client A",
            status=ClientStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    suppliers.save(
        ClientSupplier(
            id=supplier_id,
            client_id=client_id,
            name="Supplier 1",
            status=ClientSupplierStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
    )
    return client_id, supplier_id, clients, suppliers


def test_create_draft_and_activate_single_active() -> None:
    client_id, supplier_id, clients, suppliers = _seed_client_supplier()
    profiles = MemorySupplierExtractionProfileRepository()
    create = CreateSupplierExtractionProfileVersionUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
        clock=_Clock(),
    )
    activate = ActivateSupplierExtractionProfileVersionUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
    )
    list_uc = ListSupplierExtractionProfilesUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
    )

    cfg = default_extraction_configuration().to_public_dict()
    draft = create.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id=client_id,
            supplier_id=supplier_id,
            configuration=cfg,
            visual_notes="notas",
            activate=False,
            created_by="admin",
        )
    )
    assert draft.status is ExtractionProfileStatus.DRAFT
    assert draft.version == 1

    active = activate.execute(
        ActivateSupplierExtractionProfileVersionCommand(
            client_id=client_id,
            supplier_id=supplier_id,
            profile_id=draft.id,
            activated_by="admin",
        )
    )
    assert active.status is ExtractionProfileStatus.ACTIVE

    v2 = create.execute(
        CreateSupplierExtractionProfileVersionCommand(
            client_id=client_id,
            supplier_id=supplier_id,
            configuration=cfg,
            visual_notes=None,
            activate=True,
            created_by="admin",
        )
    )
    assert v2.status is ExtractionProfileStatus.ACTIVE
    assert v2.version == 2
    rows = list_uc.execute(
        ListSupplierExtractionProfilesCommand(client_id=client_id, supplier_id=supplier_id)
    )
    actives = [r for r in rows if r.status is ExtractionProfileStatus.ACTIVE]
    assert len(actives) == 1
    assert actives[0].version == 2
    superseded = [r for r in rows if r.status is ExtractionProfileStatus.SUPERSEDED]
    assert any(r.version == 1 for r in superseded)


def test_quantity_default_rejected_on_create() -> None:
    client_id, supplier_id, clients, suppliers = _seed_client_supplier()
    profiles = MemorySupplierExtractionProfileRepository()
    create = CreateSupplierExtractionProfileVersionUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
        clock=_Clock(),
    )
    cfg = default_extraction_configuration().to_public_dict()
    cfg["quantity_rules"]["default_value"] = 1
    with pytest.raises(SupplierExtractionProfileInvalidConfigurationError):
        create.execute(
            CreateSupplierExtractionProfileVersionCommand(
                client_id=client_id,
                supplier_id=supplier_id,
                configuration=cfg,
                activate=False,
                created_by="admin",
            )
        )
