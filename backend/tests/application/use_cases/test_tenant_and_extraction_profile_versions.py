"""Phase 6 — multi-tenant annotation replace + create_next_version (memory)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.errors import SupplierExtractionProfileNotFoundError
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    ReplaceSupplierReferenceAnnotationsCommand,
    ReplaceSupplierReferenceAnnotationsUseCase,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    SupplierExtractionProfile,
    default_extraction_configuration,
)
from src.infrastructure.repositories.memory_supplier_extraction_profile_repository import (
    MemorySupplierExtractionProfileRepository,
    MemorySupplierReferenceAnnotationRepository,
)


def test_create_next_version_allocates_sequential_versions() -> None:
    profiles = MemorySupplierExtractionProfileRepository()
    now = datetime.now(timezone.utc)
    first = profiles.create_next_version(
        client_id="c",
        supplier_id="s",
        profile_key="default",
        configuration=default_extraction_configuration(),
        visual_notes=None,
        created_by="u",
        created_at=now,
        profile_id=str(uuid4()),
    )
    assert first.version == 1
    second = profiles.create_next_version(
        client_id="c",
        supplier_id="s",
        profile_key="default",
        configuration=default_extraction_configuration(),
        visual_notes=None,
        created_by="u",
        created_at=now,
    )
    assert second.version == 2


def test_create_next_version_detects_collision(monkeypatch) -> None:
    profiles = MemorySupplierExtractionProfileRepository()
    now = datetime.now(timezone.utc)
    profiles.create_next_version(
        client_id="c",
        supplier_id="s",
        profile_key="default",
        configuration=default_extraction_configuration(),
        visual_notes=None,
        created_by="u",
        created_at=now,
    )
    monkeypatch.setattr(profiles, "next_version", lambda *_a, **_k: 1)
    from src.application.errors import SupplierExtractionProfileVersionConflictError

    with pytest.raises(SupplierExtractionProfileVersionConflictError):
        profiles.create_next_version(
            client_id="c",
            supplier_id="s",
            profile_key="default",
            configuration=default_extraction_configuration(),
            visual_notes=None,
            created_by="u",
            created_at=now,
        )

def test_replace_annotations_rejects_foreign_profile_id() -> None:
    """profile_id from another tenant must not be accepted when profile_repo is wired."""
    from unittest.mock import MagicMock

    profile_repo = MagicMock()
    foreign = SupplierExtractionProfile(
        id="prof-b",
        client_id="client-b",
        supplier_id="sup-b",
        profile_key="default",
        version=1,
        status=ExtractionProfileStatus.ACTIVE,
        configuration=default_extraction_configuration(),
        visual_notes=None,
        created_by="t",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    profile_repo.get_by_id.return_value = foreign

    client_repo = MagicMock()
    client_repo.get_by_id.return_value = MagicMock()
    supplier_repo = MagicMock()
    supplier = MagicMock()
    supplier.client_id = "client-a"
    supplier_repo.get_by_id.return_value = supplier
    reference_repo = MagicMock()
    image = MagicMock()
    image.client_supplier_id = "sup-a"
    reference_repo.get_by_id.return_value = image
    annotation_repo = MemorySupplierReferenceAnnotationRepository()

    uc = ReplaceSupplierReferenceAnnotationsUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        reference_repo=reference_repo,
        annotation_repo=annotation_repo,
        profile_repo=profile_repo,
    )
    with pytest.raises(SupplierExtractionProfileNotFoundError):
        uc.execute(
            ReplaceSupplierReferenceAnnotationsCommand(
                client_id="client-a",
                supplier_id="sup-a",
                image_id="img-a",
                profile_id="prof-b",
                annotations=[
                    {
                        "field_key": "ean",
                        "anchor_texts": ["EAN"],
                        "spatial_relation": "RIGHT_OF",
                        "normalized_polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
                        "priority": 1,
                    }
                ],
            )
        )
