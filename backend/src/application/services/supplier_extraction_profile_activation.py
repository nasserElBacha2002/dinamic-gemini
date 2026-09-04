"""Atomic activation of supplier extraction profiles + effective label source wiring."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from src.application.services.supplier_label_profile_wiring import (
    upsert_effective_label_source,
)
from src.domain.client_supplier.extraction_profile import SupplierExtractionProfile
from src.domain.label_profiles.kinds import LabelProfileSource, effective_label_kind
from src.infrastructure.repositories.memory_client_supplier_label_profile_repository import (
    MemoryClientSupplierLabelProfileRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)
from src.infrastructure.repositories.sql_client_supplier_label_profile_repository import (
    SqlClientSupplierLabelProfileRepository,
)
from src.infrastructure.repositories.sql_supplier_extraction_profile_repository import (
    SqlSupplierExtractionProfileRepository,
)

if TYPE_CHECKING:
    from src.application.ports.client_supplier_label_profile_repository import (
        ClientSupplierLabelProfileRepository,
    )
    from src.application.ports.clock import Clock
    from src.application.ports.supplier_extraction_profile_repository import (
        SupplierExtractionProfileRepository,
    )
    from src.database.sqlserver import SqlServerClient


def activate_profile_with_effective_source(
    *,
    profile_repo: SupplierExtractionProfileRepository,
    label_profile_repo: ClientSupplierLabelProfileRepository | None,
    clock: Clock,
    sql_client: SqlServerClient | None,
    client_id: str,
    supplier_id: str,
    profile_id: str,
    activated_by: str | None,
    expected_row_version: int | None,
    effective_source: LabelProfileSource,
) -> SupplierExtractionProfile:
    """Activate profile version and persist effective source in one unit of work."""
    if label_profile_repo is None:
        return profile_repo.activate_version(
            client_id=client_id,
            supplier_id=supplier_id,
            profile_id=profile_id,
            activated_by=activated_by,
            expected_row_version=expected_row_version,
        )

    if sql_client is not None and isinstance(
        profile_repo, SqlSupplierExtractionProfileRepository
    ):
        return _activate_sql_transaction(
            sql_client=sql_client,
            client_id=client_id,
            supplier_id=supplier_id,
            profile_id=profile_id,
            activated_by=activated_by,
            expected_row_version=expected_row_version,
            effective_source=effective_source,
            clock=clock,
        )

    return _activate_memory_transaction(
        profile_repo=profile_repo,
        label_profile_repo=label_profile_repo,
        clock=clock,
        client_id=client_id,
        supplier_id=supplier_id,
        profile_id=profile_id,
        activated_by=activated_by,
        expected_row_version=expected_row_version,
        effective_source=effective_source,
    )


def _activate_sql_transaction(
    *,
    sql_client: SqlServerClient,
    client_id: str,
    supplier_id: str,
    profile_id: str,
    activated_by: str | None,
    expected_row_version: int | None,
    effective_source: LabelProfileSource,
    clock: Clock,
) -> SupplierExtractionProfile:
    with sql_client.begin_transaction() as tx:
        profile_repo = SqlSupplierExtractionProfileRepository(
            sql_client, connection=tx.connection
        )
        label_repo = SqlClientSupplierLabelProfileRepository(
            sql_client, connection=tx.connection
        )
        activated = profile_repo.activate_version(
            client_id=client_id,
            supplier_id=supplier_id,
            profile_id=profile_id,
            activated_by=activated_by,
            expected_row_version=expected_row_version,
        )
        upsert_effective_label_source(
            label_profile_repo=label_repo,
            clock=clock,
            client_supplier_id=supplier_id,
            label_kind=effective_label_kind(activated.label_kind),
            source=effective_source,
        )
        tx.commit()
        return activated


def _activate_memory_transaction(
    *,
    profile_repo: SupplierExtractionProfileRepository,
    label_profile_repo: ClientSupplierLabelProfileRepository,
    clock: Clock,
    client_id: str,
    supplier_id: str,
    profile_id: str,
    activated_by: str | None,
    expected_row_version: int | None,
    effective_source: LabelProfileSource,
) -> SupplierExtractionProfile:
    if not isinstance(profile_repo, MemorySupplierExtractionProfileRepository):
        raise TypeError("memory activation requires MemorySupplierExtractionProfileRepository")
    if not isinstance(label_profile_repo, MemoryClientSupplierLabelProfileRepository):
        raise TypeError("memory activation requires MemoryClientSupplierLabelProfileRepository")

    profile_snapshot = deepcopy(profile_repo._rows)
    label_snapshot = deepcopy(label_profile_repo._by_key)
    try:
        activated = profile_repo.activate_version(
            client_id=client_id,
            supplier_id=supplier_id,
            profile_id=profile_id,
            activated_by=activated_by,
            expected_row_version=expected_row_version,
        )
        upsert_effective_label_source(
            label_profile_repo=label_profile_repo,
            clock=clock,
            client_supplier_id=supplier_id,
            label_kind=effective_label_kind(activated.label_kind),
            source=effective_source,
        )
        return activated
    except Exception:
        profile_repo._rows = profile_snapshot
        label_profile_repo._by_key = label_snapshot
        raise


__all__ = ["activate_profile_with_effective_source"]
