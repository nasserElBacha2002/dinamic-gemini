"""Unit tests for ClientSupplier label profile list/upsert semantics (Phase 1 corrections)."""

from __future__ import annotations

from datetime import datetime, timezone

from src.application.use_cases.suppliers.manage_client_supplier_label_profiles import (
    ListClientSupplierLabelProfilesCommand,
    ListClientSupplierLabelProfilesUseCase,
    UpsertClientSupplierLabelProfileCommand,
    UpsertClientSupplierLabelProfileUseCase,
)
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
    MemoryClientSupplierLabelProfileRepository,
)
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from tests.application.use_cases.test_aisle_processing import FixedClock

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _seed_supplier(repo: MemoryClientSupplierRepository, *, client_id: str, supplier_id: str) -> None:
    repo.save(
        ClientSupplier(
            id=supplier_id,
            client_id=client_id,
            name="Supplier",
            status=ClientSupplierStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def test_list_virtual_dinamic_defaults_have_null_timestamps() -> None:
    supplier_repo = MemoryClientSupplierRepository()
    profile_repo = MemoryClientSupplierLabelProfileRepository()
    _seed_supplier(supplier_repo, client_id="c1", supplier_id="s1")
    rows = ListClientSupplierLabelProfilesUseCase(
        client_supplier_repo=supplier_repo,
        label_profile_repo=profile_repo,
    ).execute(ListClientSupplierLabelProfilesCommand(client_id="c1", supplier_id="s1"))
    assert len(rows) == 2
    for row in rows:
        assert row.source is LabelProfileSource.DINAMIC
        assert row.id == ""
        assert row.updated_at is None
        assert row.created_at is None


def test_upsert_dinamic_deletes_row_and_returns_virtual_default() -> None:
    supplier_repo = MemoryClientSupplierRepository()
    profile_repo = MemoryClientSupplierLabelProfileRepository()
    _seed_supplier(supplier_repo, client_id="c1", supplier_id="s1")
    uc = UpsertClientSupplierLabelProfileUseCase(
        client_supplier_repo=supplier_repo,
        label_profile_repo=profile_repo,
        clock=FixedClock(_NOW),
    )
    uc.execute(
        UpsertClientSupplierLabelProfileCommand(
            client_id="c1",
            supplier_id="s1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.SUPPLIER,
        )
    )
    row = uc.execute(
        UpsertClientSupplierLabelProfileCommand(
            client_id="c1",
            supplier_id="s1",
            label_kind=LabelKind.ITEM,
            source=LabelProfileSource.DINAMIC,
        )
    )
    assert row.source is LabelProfileSource.DINAMIC
    assert row.id == ""
    assert row.updated_at is None
    assert profile_repo.get_by_supplier_and_kind("s1", LabelKind.ITEM) is None
