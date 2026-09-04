"""Persist effective label source wiring for client suppliers."""

from __future__ import annotations

import logging
from uuid import uuid4

from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.clock import Clock
from src.domain.label_profiles.entities import ClientSupplierLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

logger = logging.getLogger(__name__)


def upsert_effective_label_source(
    *,
    label_profile_repo: ClientSupplierLabelProfileRepository,
    clock: Clock,
    client_supplier_id: str,
    label_kind: LabelKind,
    source: LabelProfileSource,
) -> ClientSupplierLabelProfile:
    """Upsert ``client_supplier_label_profiles`` with the user-selected effective source."""
    supplier_id = (client_supplier_id or "").strip()
    if not supplier_id:
        raise ValueError("client_supplier_id required for label profile wiring")

    existing = label_profile_repo.get_by_supplier_and_kind(supplier_id, label_kind)
    now = clock.now()
    profile = ClientSupplierLabelProfile(
        id=existing.id if existing else str(uuid4()),
        client_supplier_id=supplier_id,
        label_kind=label_kind,
        source=source,
        created_at=existing.created_at if existing else now,
        updated_at=now,
    )
    saved = label_profile_repo.upsert(profile)
    logger.info(
        "supplier_label_profile.wired client_supplier_id=%s label_kind=%s source=%s",
        supplier_id,
        label_kind.value,
        source.value,
    )
    return saved


def detect_supplier_wiring_mismatch(
    *,
    client_supplier_id: str | None,
    item_source: LabelProfileSource,
    position_source: LabelProfileSource,
    active_extraction_kinds: set[LabelKind],
    explicit_wiring_kinds: set[LabelKind],
) -> list[str]:
    """Warn when ACTIVE profiles exist but wiring was never explicitly configured.

    Intentional ``source=DINAMIC`` rows (explicit user choice) do not produce warnings.
    """
    if not client_supplier_id or not active_extraction_kinds:
        return []
    warnings: list[str] = []
    if (
        LabelKind.ITEM in active_extraction_kinds
        and item_source is LabelProfileSource.DINAMIC
        and LabelKind.ITEM not in explicit_wiring_kinds
    ):
        warnings.append(
            "ACTIVE ITEM extraction profile exists but label_profiles.item.source=DINAMIC "
            "(no explicit client_supplier_label_profiles row)"
        )
    if (
        LabelKind.POSITION in active_extraction_kinds
        and position_source is LabelProfileSource.DINAMIC
        and LabelKind.POSITION not in explicit_wiring_kinds
    ):
        warnings.append(
            "ACTIVE POSITION extraction profile exists but label_profiles.position.source=DINAMIC "
            "(no explicit client_supplier_label_profiles row)"
        )
    return warnings


__all__ = [
    "detect_supplier_wiring_mismatch",
    "upsert_effective_label_source",
]
