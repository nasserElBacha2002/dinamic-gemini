"""SQL-backed scope and status behavior for canonical position resolution."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.services.position_label_detection.resolver import PositionLabelResolver
from src.application.services.position_recognition import (
    CanonicalPositionValidationCommand,
    CanonicalPositionValidator,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningConfig,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.payload import build_positioning_label_payload
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
)
from src.domain.label_validation import CandidateLabel
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_recognition import (
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
)
from src.infrastructure.repositories.sql_client_position_label_repository import (
    SqlClientPositionLabelRepository,
)
from src.infrastructure.repositories.sql_client_repository import SqlClientRepository
from tests.support.sql_integration import sql_server_client_or_skip
from tests.support.sql_migration_fixture import ensure_sql_migrations_applied
from tests.support.sqlserver_test_connection import resolved_sqlserver_connection_string_for_tests

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sql_client():
    client = sql_server_client_or_skip(resolved_sqlserver_connection_string_for_tests())
    ensure_sql_migrations_applied(client)
    return client


def test_sql_resolver_scopes_status_and_database_identifier_collation(sql_client) -> None:
    now = datetime.now(timezone.utc)
    token = uuid4().hex
    client_ids = [str(uuid4()), str(uuid4())]
    active_id = str(uuid4())
    inactive_id = str(uuid4())
    public_identifier = f"Pos_Case_{token}"
    signing = PositioningLabelSigningService(
        PositioningLabelSigningConfig(
            secret="integration-position-secret",
            key_version=1,
        )
    )
    signed_payload = signing.sign_payload(
        build_positioning_label_payload(public_label_id=public_identifier)
    )
    client_repo = SqlClientRepository(sql_client)
    repo = SqlClientPositionLabelRepository(sql_client)
    resolver = PositionLabelResolver(label_repo=repo)
    labels = [
        ClientPositionLabel(
            id=active_id,
            client_id=client_ids[0],
            public_identifier=public_identifier,
            name=f"Position {token}",
            normalized_name=f"POSITION {token}".upper(),
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=1,
            canonical_payload=signed_payload,
            created_at=now,
            updated_at=now,
            signature=signed_payload["signature"],
            signature_key_version=1,
            signature_status=ClientPositionLabelSignatureStatus.SIGNED,
        ),
        ClientPositionLabel(
            id=inactive_id,
            client_id=client_ids[0],
            public_identifier=f"INACTIVE_{token}",
            name=f"Inactive {token}",
            normalized_name=f"INACTIVE {token}".upper(),
            status=ClientPositionLabelStatus.INVALIDATED,
            payload_version=1,
            canonical_payload={"label_id": f"INACTIVE_{token}"},
            created_at=now,
            updated_at=now,
            invalidated_at=now,
            invalidation_reason="integration_test",
        ),
    ]
    try:
        for index, client_id in enumerate(client_ids):
            client_repo.save(
                Client(
                    id=client_id,
                    name=f"Position resolver integration {index} {token}",
                    status=ClientStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
            )
        repo.save_many(labels)

        assert (
            resolver.resolve(
                public_label_id=public_identifier,
                expected_client_id=client_ids[0],
            ).detection_status
            is PositionLabelDetectionStatus.VALID
        )
        assert (
            resolver.resolve(
                public_label_id=public_identifier,
                expected_client_id=client_ids[1],
            ).detection_status
            is PositionLabelDetectionStatus.CLIENT_MISMATCH
        )
        assert (
            resolver.resolve(
                public_label_id=f"MISSING_{token}",
                expected_client_id=client_ids[0],
            ).detection_status
            is PositionLabelDetectionStatus.LABEL_NOT_FOUND
        )
        assert (
            resolver.resolve(
                public_label_id=f"INACTIVE_{token}",
                expected_client_id=client_ids[0],
            ).detection_status
            is PositionLabelDetectionStatus.LABEL_INVALIDATED
        )

        swapped = public_identifier.swapcase()
        case_result = resolver.resolve(
            public_label_id=swapped,
            expected_client_id=client_ids[0],
        )
        assert case_result.detection_status is PositionLabelDetectionStatus.VALID

        vision = CanonicalPositionValidator(
            signing=signing,
            resolver=resolver,
        ).validate(
            CanonicalPositionValidationCommand(
                candidate=CandidateLabel(raw_payload=json.dumps(signed_payload)),
                source=PositionRecognitionSource.VISION,
                context=LabelValidationContext(
                    client_id=client_ids[0],
                    resolved_profiles=None,
                ),
            )
        )
        assert vision.status is CanonicalPositionValidationStatus.VALID_EXISTING
    finally:
        with sql_client.cursor() as cursor:
            cursor.execute(
                "DELETE FROM client_position_labels WHERE id IN (?, ?)",
                (active_id, inactive_id),
            )
            cursor.execute(
                "DELETE FROM clients WHERE id IN (?, ?)",
                (client_ids[0], client_ids[1]),
            )
