"""PR2 — non-persistent label recognition tester API / use case."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientSupplierNotFoundError,
    SupplierExtractionProfileNotFoundError,
)
from src.application.use_cases.suppliers.test_label_recognition_code import (
    LabelRecognitionCodeTestCommand,
    LabelRecognitionCodeTesterUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
    gs1_sscc_template,
)
from src.domain.label_profiles.kinds import LabelKind
from src.infrastructure.repositories.memory_client_repository import MemoryClientRepository
from src.infrastructure.repositories.memory_client_supplier_repository import (
    MemoryClientSupplierRepository,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
)

_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
_VALID_SSCC = "000123456700000008"


def _setup():
    clients = MemoryClientRepository()
    suppliers = MemoryClientSupplierRepository()
    profiles = MemorySupplierExtractionProfileRepository()
    clients.save(
        Client(
            id="client-1",
            name="C1",
            status=ClientStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    suppliers.save(
        ClientSupplier(
            id="sup-1",
            client_id="client-1",
            name="S1",
            status=ClientSupplierStatus.ACTIVE,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )
    return clients, suppliers, profiles


def test_tester_gs1_sscc_draft_config_non_persistent() -> None:
    clients, suppliers, profiles = _setup()
    uc = LabelRecognitionCodeTesterUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
    )
    out = uc.execute(
        LabelRecognitionCodeTestCommand(
            client_id="client-1",
            supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            raw_payload=f"(00){_VALID_SSCC}",
            symbology="CODE_128",
            configuration=gs1_sscc_template().to_public_dict(),
        )
    )
    assert out["persists_inventory"] is False
    assert out["structure"] == "GS1"
    assert out["validation_status"] == "VALID"
    assert out["extracted_fields"]["label_id"] == _VALID_SSCC
    assert out["extracted_fields"]["sku"] is None
    assert out["application_identifiers"] == ["00"]
    assert list(profiles.list_by_supplier("client-1", "sup-1")) == []


def test_tester_cross_tenant_rejected() -> None:
    clients, suppliers, profiles = _setup()
    uc = LabelRecognitionCodeTesterUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
    )
    with pytest.raises((ClientSupplierNotFoundError, Exception)):
        uc.execute(
            LabelRecognitionCodeTestCommand(
                client_id="client-1",
                supplier_id="other-sup",
                label_kind=LabelKind.ITEM,
                raw_payload="ABC",
                configuration={"required_fields": ["sku"]},
            )
        )


def test_tester_profile_ownership() -> None:
    clients, suppliers, profiles = _setup()
    profile = SupplierExtractionProfile(
        id="prof-1",
        client_id="client-1",
        supplier_id="sup-1",
        profile_key="default",
        version=1,
        status=ExtractionProfileStatus.DRAFT,
        configuration=gs1_sscc_template(),
        visual_notes=None,
        created_by="t",
        created_at=_NOW,
        label_kind=LabelKind.ITEM,
    )
    profiles.save(profile)
    uc = LabelRecognitionCodeTesterUseCase(
        client_repo=clients,
        client_supplier_repo=suppliers,
        profile_repo=profiles,
    )
    out = uc.execute(
        LabelRecognitionCodeTestCommand(
            client_id="client-1",
            supplier_id="sup-1",
            label_kind=LabelKind.ITEM,
            raw_payload=f"(00){_VALID_SSCC}",
            symbology="CODE_128",
            profile_id="prof-1",
        )
    )
    assert out["validation_status"] == "VALID"

    with pytest.raises(SupplierExtractionProfileNotFoundError):
        uc.execute(
            LabelRecognitionCodeTestCommand(
                client_id="client-1",
                supplier_id="sup-1",
                label_kind=LabelKind.ITEM,
                raw_payload=f"(00){_VALID_SSCC}",
                profile_id="missing",
            )
        )
