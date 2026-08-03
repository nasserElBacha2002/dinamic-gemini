"""Client-scoped positioning label create/list/get/update/invalidate."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    ClientNotFoundError,
    ClientPositionLabelAccessDeniedError,
    ClientPositionLabelConflictError,
    ClientPositionLabelNotFoundError,
    IdempotencyKeyReusedError,
)
from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.services.image_processing.processing_action_idempotency_service import (
    hash_request_payload,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningError,
    PositioningLabelSigningService,
)
from src.domain.aisle_location.label_entities import POSITIONING_LABEL_PAYLOAD_VERSION
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    payload_sha256,
    validate_positioning_payload,
)
from src.domain.client.entities import Client
from src.domain.client_position_label.entities import (
    ClientPositionLabel,
    ClientPositionLabelSignatureStatus,
    ClientPositionLabelStatus,
    normalize_position_label_name,
)

logger = logging.getLogger(__name__)

_CREATE_OP = "CREATE_CLIENT_POSITION_LABEL"
_MAX_NAME_LEN = 200
_MAX_DESCRIPTION_LEN = 1000


def require_client_scope(
    *,
    client_id: str,
    principal: AccessPrincipal,
    client_repo: ClientRepository,
) -> Client:
    cid = (client_id or "").strip()
    client = client_repo.get_by_id(cid)
    if client is None:
        raise ClientNotFoundError(f"Client not found: {cid}")
    if principal.is_platform:
        return client
    principal_client = (principal.client_id or "").strip() or None
    if principal_client is None or principal_client != cid:
        raise ClientPositionLabelAccessDeniedError(
            "Actor is not authorized for this client's position labels"
        )
    return client


@dataclass(frozen=True)
class CreateClientPositionLabelCommand:
    client_id: str
    name: str
    principal: AccessPrincipal
    description: str | None = None
    idempotency_key: str | None = None
    created_by: str | None = None


@dataclass(frozen=True)
class ListClientPositionLabelsCommand:
    client_id: str
    principal: AccessPrincipal
    status: str | None = None
    search: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetClientPositionLabelCommand:
    client_id: str
    label_id: str
    principal: AccessPrincipal


@dataclass(frozen=True)
class UpdateClientPositionLabelMetadataCommand:
    client_id: str
    label_id: str
    principal: AccessPrincipal
    name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class InvalidateClientPositionLabelCommand:
    client_id: str
    label_id: str
    principal: AccessPrincipal
    reason: str | None = None


class CreateClientPositionLabelUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
        clock: Clock,
        signing: PositioningLabelSigningService | None = None,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo
        self._clock = clock
        self._signing = signing

    @staticmethod
    def _request_hash(*, client_id: str, name: str, description: str | None) -> str:
        return hash_request_payload(
            {
                "op": _CREATE_OP,
                "client_id": client_id,
                "name": name,
                "description": description or "",
                "payload_version": POSITIONING_LABEL_PAYLOAD_VERSION,
            }
        )

    @staticmethod
    def _resolve_idempotent(
        existing: ClientPositionLabel, *, request_hash: str
    ) -> ClientPositionLabel:
        if (existing.idempotency_request_hash or "") == request_hash:
            return existing
        raise IdempotencyKeyReusedError(
            "IDEMPOTENCY_KEY_REUSED: same key with a different create fingerprint"
        )

    def execute(self, command: CreateClientPositionLabelCommand) -> ClientPositionLabel:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        name = (command.name or "").strip()
        if not name:
            raise ClientPositionLabelConflictError(
                "name is required",
                code="POSITION_LABEL_NAME_REQUIRED",
            )
        if len(name) > _MAX_NAME_LEN:
            raise ClientPositionLabelConflictError(
                f"name must be at most {_MAX_NAME_LEN} characters",
                code="POSITION_LABEL_NAME_REQUIRED",
            )
        description = (command.description or "").strip() or None
        if description is not None and len(description) > _MAX_DESCRIPTION_LEN:
            raise ClientPositionLabelConflictError(
                f"description must be at most {_MAX_DESCRIPTION_LEN} characters",
                code="POSITION_LABEL_NAME_REQUIRED",
            )
        normalized = normalize_position_label_name(name)

        idem_key = (command.idempotency_key or "").strip() or None
        request_hash: str | None = None
        if idem_key:
            request_hash = self._request_hash(
                client_id=command.client_id, name=name, description=description
            )
            existing = self._label_repo.get_by_idempotency_key(command.client_id, idem_key)
            if existing is not None:
                return self._resolve_idempotent(existing, request_hash=request_hash)

        duplicate = self._label_repo.get_active_by_normalized_name(command.client_id, normalized)
        if duplicate is not None:
            raise ClientPositionLabelConflictError(
                f"Active position label with name {normalized} already exists",
                code="POSITION_LABEL_NAME_CONFLICT",
            )

        public_identifier = f"pos_{secrets.token_urlsafe(12)}"
        payload = build_positioning_label_payload(
            public_label_id=public_identifier,
            version=POSITIONING_LABEL_PAYLOAD_VERSION,
        )
        if self._signing is not None and self._signing.can_sign:
            payload = self._signing.sign_payload(payload)
            signature_status = ClientPositionLabelSignatureStatus.SIGNED
        elif self._signing is not None and self._signing.required:
            raise PositioningLabelSigningError(
                "POSITIONING_LABEL_HMAC_SECRET is required but not configured"
            )
        else:
            signature_status = ClientPositionLabelSignatureStatus.UNSIGNED
        validate_positioning_payload(payload)

        now = self._clock.now()
        label = ClientPositionLabel(
            id=str(uuid4()),
            client_id=command.client_id,
            public_identifier=public_identifier,
            name=name,
            normalized_name=normalized,
            status=ClientPositionLabelStatus.ACTIVE,
            payload_version=POSITIONING_LABEL_PAYLOAD_VERSION,
            canonical_payload=payload,
            created_at=now,
            updated_at=now,
            description=description,
            payload_hash=payload_sha256(payload),
            signature=str(payload.get("signature") or "") or None,
            signature_algorithm="HMAC-SHA256" if signature_status.value == "SIGNED" else None,
            signature_key_version=(
                int(payload["key_version"]) if "key_version" in payload else None
            ),
            signature_status=signature_status,
            created_by=command.created_by or command.principal.actor_id,
            idempotency_key=idem_key,
            idempotency_request_hash=request_hash,
        )
        try:
            self._label_repo.save(label)
        except IdempotencyKeyReusedError:
            if not idem_key or not request_hash:
                raise
            raced = self._label_repo.get_by_idempotency_key(command.client_id, idem_key)
            if raced is None:
                raise
            return self._resolve_idempotent(raced, request_hash=request_hash)

        logger.info(
            "position_label_created client_id=%s label_id=%s public_identifier=%s",
            label.client_id,
            label.id,
            label.public_identifier,
        )
        return label


class ListClientPositionLabelsUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo

    def execute(
        self, command: ListClientPositionLabelsCommand
    ) -> tuple[list[ClientPositionLabel], int]:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        items = self._label_repo.list_by_client(
            command.client_id,
            status=command.status,
            search=command.search,
            limit=command.limit,
            offset=command.offset,
        )
        total = self._label_repo.count_by_client(
            command.client_id, status=command.status, search=command.search
        )
        return items, total


class GetClientPositionLabelUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo

    def execute(self, command: GetClientPositionLabelCommand) -> ClientPositionLabel:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        label = self._label_repo.get_by_id(command.label_id)
        if label is None or label.client_id != command.client_id:
            raise ClientPositionLabelNotFoundError(command.label_id)
        return label


class UpdateClientPositionLabelMetadataUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
        clock: Clock,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo
        self._clock = clock

    def execute(
        self, command: UpdateClientPositionLabelMetadataCommand
    ) -> ClientPositionLabel:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        label = self._label_repo.get_by_id(command.label_id)
        if label is None or label.client_id != command.client_id:
            raise ClientPositionLabelNotFoundError(command.label_id)
        if label.status != ClientPositionLabelStatus.ACTIVE:
            raise ClientPositionLabelConflictError(
                "Cannot edit an invalidated label",
                code="POSITION_LABEL_ALREADY_INVALIDATED",
            )
        if command.name is not None:
            name = command.name.strip()
            if not name:
                raise ClientPositionLabelConflictError(
                    "name is required",
                    code="POSITION_LABEL_NAME_REQUIRED",
                )
            normalized = normalize_position_label_name(name)
            dup = self._label_repo.get_active_by_normalized_name(command.client_id, normalized)
            if dup is not None and dup.id != label.id:
                raise ClientPositionLabelConflictError(
                    f"Active position label with name {normalized} already exists",
                    code="POSITION_LABEL_NAME_CONFLICT",
                )
            label.name = name
            label.normalized_name = normalized
        if command.description is not None:
            label.description = command.description.strip() or None
        label.updated_at = self._clock.now()
        self._label_repo.save(label)
        logger.info(
            "position_label_updated client_id=%s label_id=%s",
            label.client_id,
            label.id,
        )
        return label


class InvalidateClientPositionLabelUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
        clock: Clock,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo
        self._clock = clock

    def execute(self, command: InvalidateClientPositionLabelCommand) -> ClientPositionLabel:
        require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        label = self._label_repo.get_by_id(command.label_id)
        if label is None or label.client_id != command.client_id:
            raise ClientPositionLabelNotFoundError(command.label_id)
        if label.status == ClientPositionLabelStatus.INVALIDATED:
            raise ClientPositionLabelConflictError(
                "Label is already invalidated",
                code="POSITION_LABEL_ALREADY_INVALIDATED",
            )
        now = self._clock.now()
        label.status = ClientPositionLabelStatus.INVALIDATED
        label.invalidated_at = now
        label.invalidation_reason = (command.reason or "").strip() or None
        label.updated_at = now
        self._label_repo.save(label)
        logger.info(
            "position_label_invalidated client_id=%s label_id=%s",
            label.client_id,
            label.id,
        )
        return label
