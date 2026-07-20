"""SQL Server implementation of SupplierExtractionProfileRepository — Phase 6."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
    SupplierReferenceAnnotationRepository,
)
from src.application.services.image_processing.extraction_profile_configuration import (
    parse_extraction_configuration,
)
from src.database.sqlserver import SqlServerClient
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileStatus,
    ReferenceAnnotation,
    SpatialRelation,
    SupplierExtractionProfile,
)


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _require_str(row: object, column: str) -> str:
    raw = getattr(row, column, None)
    if raw is None:
        raise ValueError(f"supplier_extraction_profiles row missing required column {column!r}")
    if isinstance(raw, str):
        value = raw.strip()
    else:
        value = str(raw).strip()
    if not value:
        raise ValueError(f"supplier_extraction_profiles row has empty {column!r}")
    return value


def _parse_status(raw: object) -> ExtractionProfileStatus:
    key = str(raw or "").strip().upper()
    return ExtractionProfileStatus(key)


def _parse_configuration_json(raw: object) -> Any:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    return json.loads(text)


def _configuration_to_json(configuration) -> str:
    return json.dumps(configuration.to_public_dict(), ensure_ascii=False)


def _parse_polygon(raw: object) -> tuple[tuple[float, float], ...] | None:
    if raw is None:
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not data:
        return None
    if not isinstance(data, (list, tuple)):
        raise ValueError("normalized_polygon_json must be a list")
    points: list[tuple[float, float]] = []
    for item in data:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("normalized_polygon_json entries must be [x, y] pairs")
        points.append((float(item[0]), float(item[1])))
    return tuple(points)


def _polygon_to_json(polygon: tuple[tuple[float, float], ...] | None) -> str | None:
    if not polygon:
        return None
    return json.dumps([[x, y] for x, y in polygon], ensure_ascii=False)


def _row_to_supplier_extraction_profile(row: object) -> SupplierExtractionProfile:
    created_at = _to_utc(getattr(row, "created_at", None))
    updated_at = _to_utc(getattr(row, "updated_at", None))
    if created_at is None:
        raise ValueError("supplier_extraction_profiles row missing required created_at")
    if updated_at is None:
        raise ValueError("supplier_extraction_profiles row missing required updated_at")
    configuration = parse_extraction_configuration(
        _parse_configuration_json(getattr(row, "configuration_json", None))
    )
    return SupplierExtractionProfile(
        id=_require_str(row, "id"),
        client_id=_require_str(row, "client_id"),
        supplier_id=_require_str(row, "supplier_id"),
        profile_key=_require_str(row, "profile_key"),
        version=int(getattr(row, "version", 0)),
        status=_parse_status(getattr(row, "status", None)),
        configuration=configuration,
        visual_notes=(getattr(row, "visual_notes", None) or "").strip() or None,
        created_by=(getattr(row, "created_by", None) or "").strip() or None,
        created_at=created_at,
        activated_by=(getattr(row, "activated_by", None) or "").strip() or None,
        activated_at=_to_utc(getattr(row, "activated_at", None)),
        superseded_at=_to_utc(getattr(row, "superseded_at", None)),
        updated_at=updated_at,
        row_version=int(getattr(row, "row_version", 1) or 1),
    )


def _row_to_reference_annotation(row: object) -> ReferenceAnnotation:
    anchor_raw = getattr(row, "anchor_texts_json", None)
    if anchor_raw is None:
        raise ValueError("supplier_reference_annotations row missing anchor_texts_json")
    anchor_data = json.loads(anchor_raw) if isinstance(anchor_raw, str) else anchor_raw
    if not isinstance(anchor_data, list):
        raise ValueError("anchor_texts_json must be a JSON array")
    anchor_texts = tuple(str(x).strip() for x in anchor_data if str(x).strip())
    spatial_key = str(getattr(row, "spatial_relation", "") or "").strip().upper()
    return ReferenceAnnotation(
        id=_require_str(row, "id"),
        template_image_id=_require_str(row, "template_image_id"),
        profile_id=(getattr(row, "profile_id", None) or "").strip() or None,
        field_key=_require_str(row, "field_key"),
        anchor_texts=anchor_texts,
        spatial_relation=SpatialRelation(spatial_key),
        normalized_polygon=_parse_polygon(getattr(row, "normalized_polygon_json", None)),
        priority=int(getattr(row, "priority", 1) or 1),
        required=bool(getattr(row, "required", False)),
        max_distance_ratio=(
            float(getattr(row, "max_distance_ratio"))
            if getattr(row, "max_distance_ratio", None) is not None
            else None
        ),
    )


_SELECT_PROFILE_COLUMNS = """
    id, client_id, supplier_id, profile_key, version, status, configuration_json,
    visual_notes, created_by, created_at, activated_by, activated_at,
    superseded_at, updated_at, row_version
"""


class SqlSupplierExtractionProfileRepository(SupplierExtractionProfileRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def save(self, profile: SupplierExtractionProfile) -> None:
        created = _to_utc(profile.created_at)
        updated = _to_utc(profile.updated_at)
        if created is None:
            raise ValueError("SupplierExtractionProfile.created_at is required")
        if updated is None:
            raise ValueError("SupplierExtractionProfile.updated_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO supplier_extraction_profiles (
                    id, client_id, supplier_id, profile_key, version, status,
                    configuration_json, visual_notes, created_by, created_at,
                    activated_by, activated_at, superseded_at, updated_at, row_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.id,
                    profile.client_id,
                    profile.supplier_id,
                    profile.profile_key,
                    int(profile.version),
                    profile.status.value,
                    _configuration_to_json(profile.configuration),
                    profile.visual_notes,
                    profile.created_by,
                    created,
                    profile.activated_by,
                    _to_utc(profile.activated_at),
                    _to_utc(profile.superseded_at),
                    updated,
                    int(profile.row_version),
                ),
            )

    def get_by_id(self, profile_id: str) -> SupplierExtractionProfile | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"SELECT {_SELECT_PROFILE_COLUMNS} FROM supplier_extraction_profiles WHERE id = ?",
                (profile_id,),
            )
            row = cur.fetchone()
        return _row_to_supplier_extraction_profile(row) if row else None

    def get_by_client_supplier_version(
        self, client_id: str, supplier_id: str, version: int
    ) -> SupplierExtractionProfile | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROFILE_COLUMNS}
                FROM supplier_extraction_profiles
                WHERE client_id = ? AND supplier_id = ? AND version = ?
                """,
                (client_id, supplier_id, int(version)),
            )
            row = cur.fetchone()
        return _row_to_supplier_extraction_profile(row) if row else None

    def get_active(
        self, client_id: str, supplier_id: str
    ) -> SupplierExtractionProfile | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROFILE_COLUMNS}
                FROM supplier_extraction_profiles
                WHERE client_id = ? AND supplier_id = ? AND status = 'ACTIVE'
                """,
                (client_id, supplier_id),
            )
            row = cur.fetchone()
        return _row_to_supplier_extraction_profile(row) if row else None

    def list_by_supplier(
        self, client_id: str, supplier_id: str
    ) -> Sequence[SupplierExtractionProfile]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROFILE_COLUMNS}
                FROM supplier_extraction_profiles
                WHERE client_id = ? AND supplier_id = ?
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                (client_id, supplier_id),
            )
            rows = cur.fetchall()
        return [_row_to_supplier_extraction_profile(row) for row in rows]

    def next_version(self, client_id: str, supplier_id: str) -> int:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(version) AS max_version
                FROM supplier_extraction_profiles
                WHERE client_id = ? AND supplier_id = ?
                """,
                (client_id, supplier_id),
            )
            row = cur.fetchone()
        if not row or getattr(row, "max_version", None) is None:
            return 1
        return int(row.max_version) + 1

    def activate_version(
        self,
        *,
        client_id: str,
        supplier_id: str,
        profile_id: str,
        activated_by: str | None,
        expected_row_version: int | None = None,
    ) -> SupplierExtractionProfile:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROFILE_COLUMNS}
                FROM supplier_extraction_profiles
                WHERE id = ?
                """,
                (profile_id,),
            )
            row = cur.fetchone()
            if (
                row is None
                or getattr(row, "client_id", None) != client_id
                or getattr(row, "supplier_id", None) != supplier_id
            ):
                raise KeyError("profile_not_found")

            current_row_version = int(getattr(row, "row_version", 0) or 0)
            if expected_row_version is not None and current_row_version != expected_row_version:
                raise ValueError("row_version_conflict")

            cur.execute(
                """
                UPDATE supplier_extraction_profiles
                SET status = 'SUPERSEDED',
                    superseded_at = SYSUTCDATETIME(),
                    updated_at = SYSUTCDATETIME(),
                    row_version = row_version + 1
                WHERE client_id = ?
                  AND supplier_id = ?
                  AND status = 'ACTIVE'
                  AND id <> ?
                """,
                (client_id, supplier_id, profile_id),
            )

            if expected_row_version is not None:
                cur.execute(
                    """
                    UPDATE supplier_extraction_profiles
                    SET status = 'ACTIVE',
                        activated_at = SYSUTCDATETIME(),
                        activated_by = ?,
                        superseded_at = NULL,
                        updated_at = SYSUTCDATETIME(),
                        row_version = row_version + 1
                    WHERE id = ?
                      AND client_id = ?
                      AND supplier_id = ?
                      AND row_version = ?
                    """,
                    (
                        (activated_by or "").strip() or None,
                        profile_id,
                        client_id,
                        supplier_id,
                        expected_row_version,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE supplier_extraction_profiles
                    SET status = 'ACTIVE',
                        activated_at = SYSUTCDATETIME(),
                        activated_by = ?,
                        superseded_at = NULL,
                        updated_at = SYSUTCDATETIME(),
                        row_version = row_version + 1
                    WHERE id = ?
                      AND client_id = ?
                      AND supplier_id = ?
                    """,
                    (
                        (activated_by or "").strip() or None,
                        profile_id,
                        client_id,
                        supplier_id,
                    ),
                )

            if int(getattr(cur, "rowcount", 0) or 0) == 0:
                raise ValueError("row_version_conflict")

            cur.execute(
                f"""
                SELECT {_SELECT_PROFILE_COLUMNS}
                FROM supplier_extraction_profiles
                WHERE id = ?
                """,
                (profile_id,),
            )
            updated_row = cur.fetchone()
        if updated_row is None:
            raise KeyError("profile_not_found")
        return _row_to_supplier_extraction_profile(updated_row)


class SqlSupplierReferenceAnnotationRepository(SupplierReferenceAnnotationRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def list_by_template(self, template_image_id: str) -> Sequence[ReferenceAnnotation]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, template_image_id, profile_id, field_key, anchor_texts_json,
                       spatial_relation, normalized_polygon_json, priority, required,
                       max_distance_ratio
                FROM supplier_reference_annotations
                WHERE template_image_id = ?
                ORDER BY priority ASC, id ASC
                """,
                (template_image_id,),
            )
            rows = cur.fetchall()
        return [_row_to_reference_annotation(row) for row in rows]

    def replace_for_template(
        self, template_image_id: str, annotations: Sequence[ReferenceAnnotation]
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                DELETE FROM supplier_reference_annotations
                WHERE template_image_id = ?
                """,
                (template_image_id,),
            )
            for annotation in annotations:
                cur.execute(
                    """
                    INSERT INTO supplier_reference_annotations (
                        id, template_image_id, profile_id, field_key, anchor_texts_json,
                        spatial_relation, normalized_polygon_json, priority, required,
                        max_distance_ratio, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, SYSUTCDATETIME(), SYSUTCDATETIME())
                    """,
                    (
                        annotation.id,
                        template_image_id,
                        annotation.profile_id,
                        annotation.field_key,
                        json.dumps(list(annotation.anchor_texts), ensure_ascii=False),
                        annotation.spatial_relation.value,
                        _polygon_to_json(annotation.normalized_polygon),
                        int(annotation.priority),
                        1 if annotation.required else 0,
                        annotation.max_distance_ratio,
                    ),
                )


__all__ = [
    "SqlSupplierExtractionProfileRepository",
    "SqlSupplierReferenceAnnotationRepository",
]
