"""Mint unique physical product labels (D1) for a client — never recycle label_id."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import ProductLabelIdCollisionError
from src.application.ports.clock import Clock
from src.application.ports.issued_product_label_repository import (
    IssuedProductLabel,
    IssuedProductLabelRepository,
)
from src.application.ports.repositories import ClientRepository
from src.application.use_cases.client_position_labels.manage import require_client_scope
from src.domain.product_labels.format import (
    PRODUCT_LABEL_FORMAT_VERSION,
    build_product_label_payload,
    compute_product_label_checksum,
    generate_product_label_id,
)

logger = logging.getLogger(__name__)

_MAX_BATCH = 50
_MAX_ID_ATTEMPTS = 8


@dataclass(frozen=True)
class IssueProductLabelsCommand:
    client_id: str
    internal_code: str
    quantity: int
    principal: AccessPrincipal
    count: int = 1
    created_by: str | None = None


@dataclass(frozen=True)
class IssuedProductLabelView:
    label_id: str
    internal_code: str
    quantity: int
    format_version: str
    checksum: str
    payload: str
    created_at: datetime


@dataclass(frozen=True)
class IssueProductLabelsResult:
    items: tuple[IssuedProductLabelView, ...]


class IssueProductLabelsUseCase:
    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        issued_repo: IssuedProductLabelRepository,
        clock: Clock,
    ) -> None:
        self._client_repo = client_repo
        self._issued_repo = issued_repo
        self._clock = clock

    def execute(self, command: IssueProductLabelsCommand) -> IssueProductLabelsResult:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )

        code = (command.internal_code or "").strip()
        if not code or "|" in code or len(code) > 48:
            raise ValueError("invalid internal_code")
        if not isinstance(command.quantity, int) or command.quantity < 1 or command.quantity > 99_999_999:
            raise ValueError("invalid quantity")
        count = int(command.count)
        if count < 1 or count > _MAX_BATCH:
            raise ValueError(f"count must be 1..{_MAX_BATCH}")

        now = self._clock.now()
        issued: list[IssuedProductLabelView] = []
        for _ in range(count):
            row = self._mint_one(
                client_id=command.client_id,
                internal_code=code,
                quantity=command.quantity,
                created_by=command.created_by,
                created_at=now,
            )
            issued.append(
                IssuedProductLabelView(
                    label_id=row.label_id,
                    internal_code=row.internal_code,
                    quantity=row.quantity,
                    format_version=row.format_version,
                    checksum=row.checksum,
                    payload=row.payload,
                    created_at=row.created_at,
                )
            )
        logger.info(
            "product_label.issued client_id=%s count=%s internal_code=%s",
            command.client_id,
            count,
            code,
        )
        return IssueProductLabelsResult(items=tuple(issued))

    def _mint_one(
        self,
        *,
        client_id: str,
        internal_code: str,
        quantity: int,
        created_by: str | None,
        created_at: datetime,
    ) -> IssuedProductLabel:
        last_exc: Exception | None = None
        for _attempt in range(_MAX_ID_ATTEMPTS):
            label_id = generate_product_label_id()
            checksum = compute_product_label_checksum(
                label_id=label_id, internal_code=internal_code, quantity=quantity
            )
            payload = build_product_label_payload(
                label_id=label_id, internal_code=internal_code, quantity=quantity
            )
            row = IssuedProductLabel(
                id=str(uuid.uuid4()),
                client_id=client_id,
                label_id=label_id,
                internal_code=internal_code,
                quantity=quantity,
                format_version=PRODUCT_LABEL_FORMAT_VERSION,
                checksum=checksum,
                payload=payload,
                created_at=created_at,
                created_by=created_by,
            )
            try:
                self._issued_repo.save(row)
                return row
            except ProductLabelIdCollisionError as exc:
                last_exc = exc
                continue
        raise RuntimeError(
            f"failed to mint unique label_id after {_MAX_ID_ATTEMPTS} attempts: {last_exc}"
        )


__all__ = [
    "IssueProductLabelsCommand",
    "IssueProductLabelsResult",
    "IssueProductLabelsUseCase",
    "IssuedProductLabelView",
]
