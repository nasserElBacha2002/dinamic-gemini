"""Phase 2 use cases: render, download, replace, batch for positioning labels."""

from __future__ import annotations

import hashlib
import io
import logging
import secrets
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    AisleLocationConflictError,
    AisleLocationLabelConflictError,
    AisleLocationLabelNotFoundError,
    AisleLocationNotFoundError,
)
from src.application.ports.aisle_location_repository import (
    AisleLocationLabelArtifactRepository,
    AisleLocationLabelReplaceUnitOfWork,
    AisleLocationLabelRepository,
    AisleLocationRepository,
)
from src.application.ports.clock import Clock
from src.application.ports.repositories import AisleRepository, InventoryRepository
from src.application.services.image_processing.processing_action_idempotency_service import (
    hash_request_payload,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.positioning_label_presets import get_positioning_label_preset
from src.application.services.positioning_label_renderer import (
    LabelFormat,
    PositioningLabelDisplayData,
    PositioningLabelRenderer,
    RenderedPositioningLabel,
)
from src.application.services.positioning_label_signing import (
    PositioningLabelSigningError,
    PositioningLabelSigningService,
)
from src.application.use_cases.aisle_locations.manage_aisle_locations import (
    IssueAisleLocationLabelCommand,
    IssueAisleLocationLabelUseCase,
)
from src.domain.aisle_location.artifact_entities import (
    AisleLocationLabelArtifact,
    AisleLocationLabelArtifactStatus,
)
from src.domain.aisle_location.entities import AisleLocationStatus
from src.domain.aisle_location.label_entities import (
    POSITIONING_LABEL_PAYLOAD_VERSION,
    AisleLocationLabel,
    AisleLocationLabelStatus,
    PositioningLabelSignatureStatus,
)
from src.domain.aisle_location.payload import (
    build_positioning_label_payload,
    payload_sha256,
    validate_positioning_payload,
)
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

_REPLACE_LABEL_OP = "REPLACE_AISLE_LOCATION_LABEL"
_DEFAULT_BATCH_SYNC_LIMIT = 200
_DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class RenderAisleLocationLabelCommand:
    inventory_id: str
    label_id: str
    principal: AccessPrincipal
    format: LabelFormat
    preset: str


@dataclass(frozen=True)
class GetAisleLocationLabelCommand:
    inventory_id: str
    label_id: str
    principal: AccessPrincipal


@dataclass(frozen=True)
class DownloadAisleLocationLabelCommand:
    inventory_id: str
    label_id: str
    principal: AccessPrincipal
    format: LabelFormat
    preset: str


@dataclass(frozen=True)
class ReplaceAisleLocationLabelCommand:
    inventory_id: str
    label_id: str
    principal: AccessPrincipal
    idempotency_key: str | None = None
    generated_by: str | None = None


@dataclass(frozen=True)
class BatchRenderAisleLocationLabelsCommand:
    inventory_id: str
    aisle_id: str
    principal: AccessPrincipal
    preset: str
    format: LabelFormat = "PDF"
    location_ids: tuple[str, ...] | None = None
    emit_missing: bool = False
    idempotency_key: str | None = None


@dataclass(frozen=True)
class LabelArtifactDownload:
    artifact: AisleLocationLabelArtifact
    content: bytes
    filename: str


def _storage_key(
    label_id: str, preset: str, fmt: str, template_version: int, marker_version: int
) -> str:
    ext = "pdf" if fmt.upper() == "PDF" else "png"
    return (
        f"positioning-labels/{label_id}/{preset}/{fmt.lower()}/"
        f"t{int(template_version)}_m{int(marker_version)}.{ext}"
    )


def _temp_storage_key(label_id: str, owner: str, fmt: str) -> str:
    ext = "pdf" if fmt.upper() == "PDF" else "png"
    return f"positioning-labels/tmp/{label_id}/{owner}.{ext}"


def _filename(public_id: str, preset: str, fmt: str) -> str:
    ext = "pdf" if fmt.upper() == "PDF" else "png"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in public_id)
    return f"dinamic_position_{safe}_{preset}.{ext}"


def _require_format(fmt: str) -> str:
    upper = (fmt or "").upper()
    if upper not in ("PDF", "PNG"):
        raise AisleLocationLabelConflictError(
            "format must be PDF or PNG",
            code="POSITION_LABEL_FORMAT_UNSUPPORTED",
        )
    return upper


class GetAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        access_policy: InventoryAccessPolicy,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._access_policy = access_policy

    def execute(self, command: GetAisleLocationLabelCommand) -> AisleLocationLabel:
        label = self._label_repo.get_by_id(command.label_id)
        if label is None:
            raise AisleLocationLabelNotFoundError(command.label_id)
        location = self._location_repo.get_by_id(label.location_id)
        if location is None:
            raise AisleLocationNotFoundError(label.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        return label


class RenderAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        artifact_repo: AisleLocationLabelArtifactRepository,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        artifact_store: ArtifactStore,
        renderer: PositioningLabelRenderer,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._artifact_repo = artifact_repo
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._artifact_store = artifact_store
        self._renderer = renderer
        self._access_policy = access_policy
        self._clock = clock

    def execute(self, command: RenderAisleLocationLabelCommand) -> AisleLocationLabelArtifact:
        label = self._label_repo.get_by_id(command.label_id)
        if label is None:
            raise AisleLocationLabelNotFoundError(command.label_id)
        if label.status == AisleLocationLabelStatus.INVALIDATED:
            raise AisleLocationLabelConflictError(
                "Cannot render an invalidated label",
                code="AISLE_LOCATION_LABEL_INVALIDATED",
            )
        location = self._location_repo.get_by_id(label.location_id)
        if location is None:
            raise AisleLocationNotFoundError(label.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        preset = get_positioning_label_preset(command.preset)
        fmt = _require_format(str(command.format))

        existing = self._artifact_repo.get_by_identity(
            label_id=label.id,
            format=fmt,
            preset=preset.code,
            template_version=preset.template_version,
            marker_version=int(label.marker_version),
        )
        if existing is not None and existing.status == AisleLocationLabelArtifactStatus.READY:
            if existing.storage_key:
                return existing
            raise AisleLocationLabelConflictError(
                "Artifact marked READY but storage object is missing",
                code="POSITION_LABEL_ARTIFACT_NOT_READY",
            )
        if existing is not None and existing.status == AisleLocationLabelArtifactStatus.RENDERING:
            raise AisleLocationLabelConflictError(
                "Artifact render already in progress",
                code="POSITION_LABEL_RENDER_CONFLICT",
            )

        now = self._clock.now()
        owner = f"render_{secrets.token_hex(8)}"
        pending = AisleLocationLabelArtifact(
            id=str(uuid4()),
            label_id=label.id,
            format=fmt,
            preset=preset.code,
            template_version=int(preset.template_version),
            marker_version=int(label.marker_version),
            storage_provider="",
            storage_bucket=None,
            storage_key=None,
            content_type="application/octet-stream",
            file_size_bytes=0,
            artifact_hash="",
            created_at=now,
            status=AisleLocationLabelArtifactStatus.PENDING,
            updated_at=now,
            render_owner=None,
        )
        reserved, created = self._artifact_repo.reserve_or_get(artifact=pending)
        if reserved.status == AisleLocationLabelArtifactStatus.READY and reserved.storage_key:
            return reserved
        if reserved.status == AisleLocationLabelArtifactStatus.RENDERING:
            raise AisleLocationLabelConflictError(
                "Artifact render already in progress",
                code="POSITION_LABEL_RENDER_CONFLICT",
            )

        claimed = self._artifact_repo.claim_for_render(
            artifact_id=reserved.id, render_owner=owner, now=now
        )
        if claimed is None:
            raced = self._artifact_repo.get_by_id(reserved.id)
            if raced is not None and raced.status == AisleLocationLabelArtifactStatus.READY:
                return raced
            raise AisleLocationLabelConflictError(
                "Artifact render already in progress",
                code="POSITION_LABEL_RENDER_CONFLICT",
            )

        temp_key = _temp_storage_key(label.id, owner, fmt)
        final_key = _storage_key(
            label.id, preset.code, fmt, preset.template_version, label.marker_version
        )
        try:
            inventory = self._inventory_repo.get_by_id(command.inventory_id)
            aisle = self._aisle_repo.get_by_id(location.aisle_id)
            display = PositioningLabelDisplayData(
                depot_name=(inventory.name if inventory else "") or command.inventory_id,
                aisle_code=(aisle.code if aisle else "") or location.aisle_id,
                position_code=location.code,
                public_label_id=label.public_identifier,
                payload_version=int(label.payload_version),
                marker_version=int(label.marker_version),
                template_version=int(preset.template_version),
            )
            validate_positioning_payload(label.payload)
            rendered: RenderedPositioningLabel = self._renderer.render(
                payload=label.payload,
                display=display,
                preset=preset,
                fmt=fmt,  # type: ignore[arg-type]
            )
            self._artifact_store.put_object(
                temp_key, io.BytesIO(rendered.content), rendered.content_type
            )
            # Promote temp → final key (overwrite final only after successful render).
            final_stored = self._artifact_store.put_object(
                final_key, io.BytesIO(rendered.content), rendered.content_type
            )
            try:
                self._artifact_store.delete_object(temp_key)
            except Exception:
                logger.warning(
                    "position_label_render_temp_cleanup_failed key=%s", temp_key, exc_info=True
                )

            done_at = self._clock.now()
            claimed.status = AisleLocationLabelArtifactStatus.READY
            claimed.storage_provider = final_stored.storage_provider
            claimed.storage_bucket = final_stored.storage_bucket
            claimed.storage_key = final_stored.storage_key
            claimed.content_type = rendered.content_type
            claimed.file_size_bytes = int(final_stored.file_size_bytes)
            claimed.artifact_hash = rendered.artifact_hash
            claimed.failure_code = None
            claimed.failure_detail = None
            claimed.updated_at = done_at
            claimed.render_owner = owner
            self._artifact_repo.save(claimed)
            logger.info(
                "position_label_render_completed label_id=%s format=%s preset=%s artifact_id=%s created=%s",
                label.id,
                fmt,
                preset.code,
                claimed.id,
                created,
            )
            return claimed
        except Exception as exc:
            fail_at = self._clock.now()
            claimed.status = AisleLocationLabelArtifactStatus.FAILED
            claimed.failure_code = "POSITION_LABEL_RENDER_FAILED"
            claimed.failure_detail = str(exc)[:500]
            claimed.updated_at = fail_at
            claimed.render_owner = owner
            self._artifact_repo.save(claimed)
            for key in (temp_key, final_key):
                try:
                    self._artifact_store.delete_object(key)
                except Exception:
                    logger.warning(
                        "position_label_render_cleanup_failed key=%s", key, exc_info=True
                    )
            logger.exception(
                "position_label_render_failed label_id=%s artifact_id=%s",
                label.id,
                claimed.id,
            )
            raise AisleLocationLabelConflictError(
                "Label render failed",
                code="POSITION_LABEL_RENDER_FAILED",
            ) from exc


class DownloadAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        render_use_case: RenderAisleLocationLabelUseCase,
        label_repo: AisleLocationLabelRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self._render = render_use_case
        self._label_repo = label_repo
        self._artifact_store = artifact_store

    def execute(self, command: DownloadAisleLocationLabelCommand) -> LabelArtifactDownload:
        artifact = self._render.execute(
            RenderAisleLocationLabelCommand(
                inventory_id=command.inventory_id,
                label_id=command.label_id,
                principal=command.principal,
                format=command.format,
                preset=command.preset,
            )
        )
        if (
            artifact.status != AisleLocationLabelArtifactStatus.READY
            or not artifact.storage_key
        ):
            raise AisleLocationLabelConflictError(
                "Artifact is not ready for download",
                code="POSITION_LABEL_ARTIFACT_NOT_READY",
            )
        label = self._label_repo.get_by_id(command.label_id)
        public_id = label.public_identifier if label else command.label_id
        downloaded = self._artifact_store.get_object(artifact.storage_key)
        return LabelArtifactDownload(
            artifact=artifact,
            content=downloaded.content,
            filename=_filename(public_id, artifact.preset, artifact.format),
        )


class ReplaceAisleLocationLabelUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        replace_uow: AisleLocationLabelReplaceUnitOfWork,
        access_policy: InventoryAccessPolicy,
        clock: Clock,
        signing: PositioningLabelSigningService | None = None,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._replace_uow = replace_uow
        self._access_policy = access_policy
        self._clock = clock
        self._signing = signing

    @staticmethod
    def _request_hash(*, client_id: str, old_label_id: str, location_id: str) -> str:
        return hash_request_payload(
            {
                "op": _REPLACE_LABEL_OP,
                "client_id": client_id,
                "old_label_id": old_label_id,
                "location_id": location_id,
                "payload_version": POSITIONING_LABEL_PAYLOAD_VERSION,
            }
        )

    def execute(self, command: ReplaceAisleLocationLabelCommand) -> AisleLocationLabel:
        old = self._label_repo.get_by_id(command.label_id)
        if old is None:
            raise AisleLocationLabelNotFoundError(command.label_id)
        location = self._location_repo.get_by_id(old.location_id)
        if location is None:
            raise AisleLocationNotFoundError(old.location_id)
        self._access_policy.require_aisle(
            command.inventory_id, location.aisle_id, command.principal
        )
        if not (location.public_identifier or "").strip():
            raise AisleLocationConflictError(
                "Location is missing public_identifier",
                code="AISLE_LOCATION_PUBLIC_ID_REQUIRED",
            )

        idem_key = (command.idempotency_key or "").strip() or None
        request_hash = (
            self._request_hash(
                client_id=location.client_id,
                old_label_id=old.id,
                location_id=location.id,
            )
            if idem_key
            else None
        )

        public_identifier = f"pl_{secrets.token_urlsafe(12)}"
        label_id = str(uuid4())
        payload = build_positioning_label_payload(
            public_label_id=public_identifier,
            public_position_id=location.public_identifier,
            version=POSITIONING_LABEL_PAYLOAD_VERSION,
        )
        if self._signing is not None and self._signing.can_sign:
            payload = self._signing.sign_payload(payload)
            signature_status = PositioningLabelSignatureStatus.SIGNED
        elif self._signing is not None and self._signing.required:
            raise PositioningLabelSigningError(
                "POSITIONING_LABEL_HMAC_SECRET is required but not configured"
            )
        else:
            signature_status = PositioningLabelSignatureStatus.UNSIGNED
        validate_positioning_payload(payload)
        now = self._clock.now()
        new_label = AisleLocationLabel(
            id=label_id,
            client_id=location.client_id,
            location_id=location.id,
            public_identifier=public_identifier,
            payload_version=POSITIONING_LABEL_PAYLOAD_VERSION,
            marker_version=1,
            template_version=1,
            status=AisleLocationLabelStatus.ACTIVE,
            payload=payload,
            generated_at=now,
            payload_hash=payload_sha256(payload),
            signature_status=signature_status,
            generated_by=command.generated_by or command.principal.actor_id,
            idempotency_key=idem_key,
            idempotency_request_hash=request_hash,
        )
        return self._replace_uow.replace_atomically(
            old_label_id=old.id,
            new_label=new_label,
            now=now,
            request_hash=request_hash,
            idempotency_key=idem_key,
        )


class BatchRenderAisleLocationLabelsUseCase:
    def __init__(
        self,
        *,
        location_repo: AisleLocationRepository,
        label_repo: AisleLocationLabelRepository,
        issue_use_case: IssueAisleLocationLabelUseCase,
        access_policy: InventoryAccessPolicy,
        renderer: PositioningLabelRenderer,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        artifact_store: ArtifactStore,
        clock: Clock,
        max_batch_size: int = _DEFAULT_BATCH_SYNC_LIMIT,
        max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES,
    ) -> None:
        self._location_repo = location_repo
        self._label_repo = label_repo
        self._issue = issue_use_case
        self._access_policy = access_policy
        self._renderer = renderer
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._artifact_store = artifact_store
        self._clock = clock
        self._max_batch_size = max(1, int(max_batch_size))
        self._max_pdf_bytes = max(1, int(max_pdf_bytes))

    def execute(self, command: BatchRenderAisleLocationLabelsCommand) -> LabelArtifactDownload:
        self._access_policy.require_aisle(
            command.inventory_id, command.aisle_id, command.principal
        )
        fmt = _require_format(str(command.format))
        if fmt != "PDF":
            raise AisleLocationLabelConflictError(
                "Batch render currently supports PDF only",
                code="POSITION_LABEL_FORMAT_UNSUPPORTED",
            )

        locations = self._location_repo.list_by_aisle(
            command.aisle_id,
            status=AisleLocationStatus.ACTIVE.value,
            limit=self._max_batch_size + 1,
            offset=0,
        )
        if command.location_ids:
            wanted = {lid.strip() for lid in command.location_ids if lid and lid.strip()}
            locations = [loc for loc in locations if loc.id in wanted]
            locations.sort(key=lambda loc: (loc.normalized_code, loc.id))

        if len(locations) > self._max_batch_size:
            raise AisleLocationLabelConflictError(
                f"Batch exceeds sync limit of {self._max_batch_size}",
                code="POSITION_LABEL_BATCH_TOO_LARGE",
            )

        from reportlab.lib.units import mm as rl_mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as pdf_canvas

        preset = get_positioning_label_preset(command.preset)
        inventory = self._inventory_repo.get_by_id(command.inventory_id)
        aisle = self._aisle_repo.get_by_id(command.aisle_id)
        client_id = (inventory.client_id if inventory else "") or ""

        label_by_location = self._label_repo.list_active_labels_by_location_ids(
            [loc.id for loc in locations]
        )

        request_hash = hash_request_payload(
            {
                "op": "BATCH_RENDER_AISLE_LOCATION_LABELS",
                "inventory_id": command.inventory_id,
                "aisle_id": command.aisle_id,
                "preset": preset.code,
                "format": fmt,
                "emit_missing": bool(command.emit_missing),
                "location_ids": [loc.id for loc in locations],
            }
        )
        batch_id = str(uuid4())
        idem_key = (command.idempotency_key or "").strip() or None
        if idem_key:
            # Stable batch id for storage key when caller provides idempotency key.
            batch_id = hashlib.sha256(
                f"{client_id}:{idem_key}:{request_hash}".encode()
            ).hexdigest()[:32]

        pdf_buf = io.BytesIO()
        page_w = preset.width_mm * rl_mm
        page_h = preset.height_mm * rl_mm
        c = pdf_canvas.Canvas(pdf_buf, pagesize=(page_w, page_h))
        pages = 0

        for loc in locations:
            label = label_by_location.get(loc.id)
            if label is None:
                if not command.emit_missing:
                    continue
                derived_key = f"batch:{batch_id}:{loc.id}"
                label = self._issue.execute(
                    IssueAisleLocationLabelCommand(
                        location_id=loc.id,
                        inventory_id=command.inventory_id,
                        principal=command.principal,
                        idempotency_key=derived_key,
                    )
                )
            display = PositioningLabelDisplayData(
                depot_name=(inventory.name if inventory else "") or command.inventory_id,
                aisle_code=(aisle.code if aisle else "") or command.aisle_id,
                position_code=loc.code,
                public_label_id=label.public_identifier,
                payload_version=int(label.payload_version),
                marker_version=int(label.marker_version),
                template_version=int(preset.template_version),
            )
            png = self._renderer.render(
                payload=label.payload,
                display=display,
                preset=preset,
                fmt="PNG",
            )
            c.drawImage(
                ImageReader(io.BytesIO(png.content)),
                0,
                0,
                width=page_w,
                height=page_h,
                preserveAspectRatio=True,
                anchor="c",
            )
            c.showPage()
            pages += 1

        if pages == 0:
            raise AisleLocationConflictError(
                "No labels to render in batch (set emit_missing=true to issue missing)",
                code="AISLE_LOCATION_LABEL_BATCH_EMPTY",
            )
        c.save()
        content = pdf_buf.getvalue()
        if len(content) > self._max_pdf_bytes:
            raise AisleLocationLabelConflictError(
                "Batch PDF exceeds configured size limit",
                code="POSITION_LABEL_BATCH_TOO_LARGE",
            )

        digest = hashlib.sha256(content).hexdigest()
        now = self._clock.now()
        storage_key = (
            f"positioning-labels/batches/{command.aisle_id}/{batch_id}/{preset.code}.pdf"
        )
        stored = self._artifact_store.put_object(
            storage_key, io.BytesIO(content), "application/pdf"
        )
        durable = AisleLocationLabelArtifact(
            id=batch_id if len(batch_id) == 36 else str(uuid4()),
            label_id=f"batch:{command.aisle_id}",
            format="PDF",
            preset=preset.code,
            template_version=preset.template_version,
            marker_version=1,
            storage_provider=stored.storage_provider,
            storage_bucket=stored.storage_bucket,
            storage_key=stored.storage_key,
            content_type="application/pdf",
            file_size_bytes=int(stored.file_size_bytes),
            artifact_hash=digest,
            created_at=now,
            status=AisleLocationLabelArtifactStatus.READY,
            updated_at=now,
        )
        logger.info(
            "position_label_batch_completed aisle_id=%s pages=%s bytes=%s request_hash=%s",
            command.aisle_id,
            pages,
            len(content),
            request_hash,
        )
        return LabelArtifactDownload(
            artifact=durable,
            content=content,
            filename=f"dinamic_position_batch_{command.aisle_id}_{preset.code}.pdf",
        )
