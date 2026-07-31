"""Sync render / preview / download for client-scoped positioning labels."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from uuid import uuid4

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    ClientPositionLabelConflictError,
    ClientPositionLabelNotFoundError,
)
from src.application.ports.client_position_label_repository import ClientPositionLabelRepository
from src.application.ports.clock import Clock
from src.application.ports.repositories import ClientRepository
from src.application.services.positioning_label_presets import get_positioning_label_preset
from src.application.services.positioning_label_renderer import (
    LabelFormat,
    PositioningLabelDisplayData,
    PositioningLabelRenderer,
    RenderedPositioningLabel,
)
from src.application.use_cases.client_position_labels.manage import require_client_scope
from src.domain.aisle_location.payload import validate_positioning_payload
from src.domain.client_position_label.entities import (
    ClientPositionLabelArtifact,
    ClientPositionLabelStatus,
)
from src.infrastructure.storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)

_MARKER_VERSION = 1


@dataclass(frozen=True)
class RenderClientPositionLabelCommand:
    client_id: str
    label_id: str
    principal: AccessPrincipal
    format: LabelFormat
    preset: str


@dataclass(frozen=True)
class LabelArtifactDownload:
    artifact: ClientPositionLabelArtifact
    content: bytes
    filename: str


def _storage_key(
    label_id: str, preset: str, fmt: str, template_version: int, marker_version: int
) -> str:
    ext = "pdf" if fmt.upper() == "PDF" else "png"
    return (
        f"client-position-labels/{label_id}/{preset}/{fmt.lower()}/"
        f"t{int(template_version)}_m{int(marker_version)}.{ext}"
    )


def _filename(public_id: str, preset: str, fmt: str) -> str:
    ext = "pdf" if fmt.upper() == "PDF" else "png"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in public_id)
    return f"dinamic_position_{safe}_{preset}.{ext}"


def _require_format(fmt: str) -> str:
    upper = (fmt or "").upper()
    if upper not in ("PDF", "PNG"):
        raise ClientPositionLabelConflictError(
            "format must be PDF or PNG",
            code="POSITION_LABEL_FORMAT_UNSUPPORTED",
        )
    return upper


class RenderClientPositionLabelUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
        artifact_store: ArtifactStore,
        renderer: PositioningLabelRenderer,
        clock: Clock,
    ) -> None:
        self._label_repo = label_repo
        self._client_repo = client_repo
        self._artifact_store = artifact_store
        self._renderer = renderer
        self._clock = clock

    def execute(self, command: RenderClientPositionLabelCommand) -> ClientPositionLabelArtifact:
        client = require_client_scope(
            client_id=command.client_id,
            principal=command.principal,
            client_repo=self._client_repo,
        )
        label = self._label_repo.get_by_id(command.label_id)
        if label is None or label.client_id != command.client_id:
            raise ClientPositionLabelNotFoundError(command.label_id)
        if label.status != ClientPositionLabelStatus.ACTIVE:
            raise ClientPositionLabelConflictError(
                "Cannot render an invalidated label",
                code="POSITION_LABEL_ALREADY_INVALIDATED",
            )

        preset = get_positioning_label_preset(command.preset)
        fmt = _require_format(str(command.format))
        existing = self._label_repo.get_artifact(
            label.id,
            format=fmt,
            preset=preset.code,
            template_version=int(preset.template_version),
            marker_version=_MARKER_VERSION,
        )
        if existing is not None and existing.storage_key:
            logger.info(
                "position_label_rendered client_id=%s label_id=%s format=%s cache=hit",
                label.client_id,
                label.id,
                fmt,
            )
            return existing

        try:
            validate_positioning_payload(label.canonical_payload)
            display = PositioningLabelDisplayData(
                depot_name=client.name or "",
                aisle_code="",
                position_code=label.name,
                public_label_id=label.public_identifier,
                payload_version=int(label.payload_version),
                marker_version=_MARKER_VERSION,
                template_version=int(preset.template_version),
            )
            rendered: RenderedPositioningLabel = self._renderer.render(
                payload=label.canonical_payload,
                display=display,
                preset=preset,
                fmt=fmt,  # type: ignore[arg-type]
            )
            final_key = _storage_key(
                label.id, preset.code, fmt, preset.template_version, _MARKER_VERSION
            )
            stored = self._artifact_store.put_object(
                final_key, io.BytesIO(rendered.content), rendered.content_type
            )
            artifact = ClientPositionLabelArtifact(
                id=str(uuid4()) if existing is None else existing.id,
                label_id=label.id,
                format=fmt,
                preset=preset.code,
                template_version=int(preset.template_version),
                marker_version=_MARKER_VERSION,
                content_type=rendered.content_type,
                file_size_bytes=int(stored.file_size_bytes),
                artifact_hash=rendered.artifact_hash,
                storage_key=stored.storage_key,
                created_at=self._clock.now() if existing is None else existing.created_at,
            )
            saved = self._label_repo.save_artifact(artifact)
            logger.info(
                "position_label_rendered client_id=%s label_id=%s format=%s cache=miss",
                label.client_id,
                label.id,
                fmt,
            )
            return saved
        except ClientPositionLabelConflictError:
            raise
        except Exception as exc:
            logger.exception(
                "position_label_render_failed client_id=%s label_id=%s",
                command.client_id,
                command.label_id,
            )
            raise ClientPositionLabelConflictError(
                "Label render failed",
                code="POSITION_LABEL_RENDER_FAILED",
            ) from exc


class DownloadClientPositionLabelUseCase:
    def __init__(
        self,
        *,
        label_repo: ClientPositionLabelRepository,
        client_repo: ClientRepository,
        artifact_store: ArtifactStore,
        renderer: PositioningLabelRenderer,
        clock: Clock,
    ) -> None:
        self._render = RenderClientPositionLabelUseCase(
            label_repo=label_repo,
            client_repo=client_repo,
            artifact_store=artifact_store,
            renderer=renderer,
            clock=clock,
        )
        self._label_repo = label_repo
        self._client_repo = client_repo
        self._artifact_store = artifact_store

    def execute(self, command: RenderClientPositionLabelCommand) -> LabelArtifactDownload:
        artifact = self._render.execute(command)
        label = self._label_repo.get_by_id(command.label_id)
        if label is None or label.client_id != command.client_id:
            raise ClientPositionLabelNotFoundError(command.label_id)
        content = self._artifact_store.get_object(artifact.storage_key).content
        logger.info(
            "position_label_downloaded client_id=%s label_id=%s format=%s",
            label.client_id,
            label.id,
            artifact.format,
        )
        return LabelArtifactDownload(
            artifact=artifact,
            content=content,
            filename=_filename(label.public_identifier, artifact.preset, artifact.format),
        )
