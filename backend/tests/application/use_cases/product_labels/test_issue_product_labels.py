"""IssueProductLabelsUseCase — mint unique D1 stickers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import ClientPositionLabelAccessDeniedError
from src.application.use_cases.product_labels import (
    IssueProductLabelsCommand,
    IssueProductLabelsUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.infrastructure.repositories.memory_issued_product_label_repository import (
    MemoryIssuedProductLabelRepository,
)


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Clients:
    def __init__(self) -> None:
        self._c = Client(
            id="client-1",
            name="Acme",
            status=ClientStatus.ACTIVE,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def get_by_id(self, client_id: str):
        return self._c if client_id == "client-1" else None


def _platform() -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u1",
        client_id=None,
        roles=frozenset({"admin"}),
        is_platform=True,
    )


def _company(client_id: str) -> AccessPrincipal:
    return AccessPrincipal(
        actor_id="u2",
        client_id=client_id,
        roles=frozenset({"operator"}),
        is_platform=False,
    )


def test_issue_batch_unique_label_ids() -> None:
    repo = MemoryIssuedProductLabelRepository()
    uc = IssueProductLabelsUseCase(client_repo=_Clients(), issued_repo=repo, clock=_Clock())
    result = uc.execute(
        IssueProductLabelsCommand(
            client_id="client-1",
            internal_code="SKU100",
            quantity=4,
            count=3,
            principal=_platform(),
        )
    )
    assert len(result.items) == 3
    ids = {i.label_id for i in result.items}
    assert len(ids) == 3
    for item in result.items:
        assert item.payload.startswith("D1|")
        assert item.checksum
        assert repo.get_by_label_id(item.label_id) is not None


def test_issue_single_creates_d1_payload_with_label_id_roundtrip() -> None:
    from src.domain.product_labels.format import (
        ProductLabelValidationStatus,
        parse_product_label_payload,
    )

    repo = MemoryIssuedProductLabelRepository()
    uc = IssueProductLabelsUseCase(client_repo=_Clients(), issued_repo=repo, clock=_Clock())
    result = uc.execute(
        IssueProductLabelsCommand(
            client_id="client-1",
            internal_code="12901904",
            quantity=192904,
            count=1,
            principal=_platform(),
        )
    )
    assert len(result.items) == 1
    item = result.items[0]
    assert item.label_id
    assert item.internal_code == "12901904"
    assert item.quantity == 192904
    parts = item.payload.split("|")
    assert parts[0] == "D1"
    assert parts[1] == item.label_id
    assert parts[2] == "12901904"
    assert parts[3] == "192904"
    parsed = parse_product_label_payload(item.payload)
    assert parsed.status is ProductLabelValidationStatus.VALID
    assert parsed.label_id == item.label_id
    assert parsed.internal_code == "12901904"
    assert parsed.quantity == 192904
    stored = repo.get_by_label_id(item.label_id)
    assert stored is not None
    assert stored.payload == item.payload


def test_issue_invalid_internal_code_raises() -> None:
    from src.application.errors import ProductLabelIssueValidationError

    repo = MemoryIssuedProductLabelRepository()
    uc = IssueProductLabelsUseCase(client_repo=_Clients(), issued_repo=repo, clock=_Clock())
    with pytest.raises(ProductLabelIssueValidationError, match="invalid internal_code"):
        uc.execute(
            IssueProductLabelsCommand(
                client_id="client-1",
                internal_code="bad|code",
                quantity=1,
                count=1,
                principal=_platform(),
            )
        )


def test_company_principal_denied_for_other_client() -> None:
    repo = MemoryIssuedProductLabelRepository()
    uc = IssueProductLabelsUseCase(client_repo=_Clients(), issued_repo=repo, clock=_Clock())
    with pytest.raises(ClientPositionLabelAccessDeniedError):
        uc.execute(
            IssueProductLabelsCommand(
                client_id="client-1",
                internal_code="SKU100",
                quantity=4,
                count=1,
                principal=_company("client-other"),
            )
        )

