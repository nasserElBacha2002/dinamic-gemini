"""SQL Server image position label detection repository."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pyodbc

from src.database.sqlserver import SqlServerClient
from src.domain.position_label_detection.entities import (
    ImagePositionLabelDetection,
    PositionLabelDetectionStatus,
    PositionLabelSignatureStatus,
)
from src.infrastructure.repositories.db_row_text import normalize_db_str, optional_nonempty_db_str


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def _json_dump(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else None


_SELECT = """
SELECT id, client_id, inventory_id, job_id, source_asset_id, client_image_id,
       ordered_capture_session_id, sequence_number, position_label_id, public_identifier,
       position_name_snapshot, payload_version, signature_status, detection_status,
       confidence, bounding_box_json, rotation_degrees, raw_payload_hash,
       detector_name, detector_version, metadata_json, created_at, updated_at
FROM dbo.image_position_label_detections
"""


def _row_to_entity(row) -> ImagePositionLabelDetection:
    created = _ensure_utc(getattr(row, "created_at", None))
    updated = _ensure_utc(getattr(row, "updated_at", None))
    if created is None or updated is None:
        raise ValueError("image_position_label_detections row missing timestamps")
    return ImagePositionLabelDetection(
        id=normalize_db_str(getattr(row, "id", None)),
        client_id=normalize_db_str(getattr(row, "client_id", None)),
        inventory_id=normalize_db_str(getattr(row, "inventory_id", None)),
        job_id=normalize_db_str(getattr(row, "job_id", None)),
        source_asset_id=normalize_db_str(getattr(row, "source_asset_id", None)),
        client_image_id=optional_nonempty_db_str(getattr(row, "client_image_id", None)),
        ordered_capture_session_id=optional_nonempty_db_str(
            getattr(row, "ordered_capture_session_id", None)
        ),
        sequence_number=(
            int(getattr(row, "sequence_number"))
            if getattr(row, "sequence_number", None) is not None
            else None
        ),
        position_label_id=optional_nonempty_db_str(getattr(row, "position_label_id", None)),
        public_identifier=optional_nonempty_db_str(getattr(row, "public_identifier", None)),
        position_name_snapshot=optional_nonempty_db_str(
            getattr(row, "position_name_snapshot", None)
        ),
        payload_version=(
            int(getattr(row, "payload_version"))
            if getattr(row, "payload_version", None) is not None
            else None
        ),
        signature_status=PositionLabelSignatureStatus(
            normalize_db_str(getattr(row, "signature_status", None)) or "MISSING"
        ),
        detection_status=PositionLabelDetectionStatus(
            normalize_db_str(getattr(row, "detection_status", None)) or "DETECTION_FAILED"
        ),
        confidence=(
            float(getattr(row, "confidence"))
            if getattr(row, "confidence", None) is not None
            else None
        ),
        bounding_box_json=_json_load(getattr(row, "bounding_box_json", None)),
        rotation_degrees=(
            float(getattr(row, "rotation_degrees"))
            if getattr(row, "rotation_degrees", None) is not None
            else None
        ),
        raw_payload_hash=optional_nonempty_db_str(getattr(row, "raw_payload_hash", None)),
        detector_name=normalize_db_str(getattr(row, "detector_name", None)),
        detector_version=normalize_db_str(getattr(row, "detector_version", None)),
        metadata_json=_json_load(getattr(row, "metadata_json", None)) or {},
        created_at=created,
        updated_at=updated,
    )


class SqlImagePositionLabelDetectionRepository:
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def upsert_idempotent(self, detection: ImagePositionLabelDetection) -> ImagePositionLabelDetection:
        hash_key = (detection.raw_payload_hash or "").strip() or f"status:{detection.detection_status.value}"
        detection.raw_payload_hash = hash_key
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT
                + """
                WHERE job_id = ?
                  AND source_asset_id = ?
                  AND detector_version = ?
                  AND detection_status = ?
                  AND raw_payload_hash = ?
                """,
                (
                    detection.job_id,
                    detection.source_asset_id,
                    detection.detector_version,
                    detection.detection_status.value,
                    hash_key,
                ),
            )
            existing = cur.fetchone()
            if existing is not None:
                prev = _row_to_entity(existing)
                # Preserve identity scope — never rewrite job/inventory/client/asset.
                detection.id = prev.id
                detection.created_at = prev.created_at
                detection.job_id = prev.job_id
                detection.inventory_id = prev.inventory_id
                detection.client_id = prev.client_id
                detection.source_asset_id = prev.source_asset_id
                cur.execute(
                    """
                    UPDATE dbo.image_position_label_detections
                    SET client_image_id = ?, ordered_capture_session_id = ?,
                        sequence_number = ?, position_label_id = ?, public_identifier = ?,
                        position_name_snapshot = ?, payload_version = ?, signature_status = ?,
                        confidence = ?, bounding_box_json = ?, rotation_degrees = ?,
                        detector_name = ?, metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        detection.client_image_id,
                        detection.ordered_capture_session_id,
                        detection.sequence_number,
                        detection.position_label_id,
                        detection.public_identifier,
                        detection.position_name_snapshot,
                        detection.payload_version,
                        detection.signature_status.value,
                        detection.confidence,
                        _json_dump(detection.bounding_box_json),
                        detection.rotation_degrees,
                        detection.detector_name,
                        _json_dump(detection.metadata_json or None),
                        detection.updated_at,
                        detection.id,
                    ),
                )
                return detection
            try:
                cur.execute(
                    """
                    INSERT INTO dbo.image_position_label_detections (
                        id, client_id, inventory_id, job_id, source_asset_id, client_image_id,
                        ordered_capture_session_id, sequence_number, position_label_id,
                        public_identifier, position_name_snapshot, payload_version,
                        signature_status, detection_status, confidence, bounding_box_json,
                        rotation_degrees, raw_payload_hash, detector_name, detector_version,
                        metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detection.id,
                        detection.client_id,
                        detection.inventory_id,
                        detection.job_id,
                        detection.source_asset_id,
                        detection.client_image_id,
                        detection.ordered_capture_session_id,
                        detection.sequence_number,
                        detection.position_label_id,
                        detection.public_identifier,
                        detection.position_name_snapshot,
                        detection.payload_version,
                        detection.signature_status.value,
                        detection.detection_status.value,
                        detection.confidence,
                        _json_dump(detection.bounding_box_json),
                        detection.rotation_degrees,
                        hash_key,
                        detection.detector_name,
                        detection.detector_version,
                        _json_dump(detection.metadata_json or None),
                        detection.created_at,
                        detection.updated_at,
                    ),
                )
            except pyodbc.IntegrityError:
                cur.execute(
                    _SELECT
                    + """
                    WHERE job_id = ?
                      AND source_asset_id = ?
                      AND detector_version = ?
                      AND detection_status = ?
                      AND raw_payload_hash = ?
                    """,
                    (
                        detection.job_id,
                        detection.source_asset_id,
                        detection.detector_version,
                        detection.detection_status.value,
                        hash_key,
                    ),
                )
                raced = cur.fetchone()
                if raced is None:
                    raise
                return _row_to_entity(raced)
            return detection

    def replace_asset_detections_atomically(
        self,
        *,
        job_id: str,
        source_asset_id: str,
        detector_version: str,
        detections: Sequence[ImagePositionLabelDetection],
    ) -> list[ImagePositionLabelDetection]:
        with self._client.begin_transaction() as txn:
            cur = txn.connection.cursor()
            out: list[ImagePositionLabelDetection] = []
            kept_ids: list[str] = []
            for detection in detections:
                hash_key = (detection.raw_payload_hash or "").strip() or (
                    f"status:{detection.detection_status.value}"
                )
                detection.raw_payload_hash = hash_key
                cur.execute(
                    _SELECT
                    + """
                    WHERE job_id = ?
                      AND source_asset_id = ?
                      AND detector_version = ?
                      AND detection_status = ?
                      AND raw_payload_hash = ?
                    """,
                    (
                        detection.job_id,
                        detection.source_asset_id,
                        detection.detector_version,
                        detection.detection_status.value,
                        hash_key,
                    ),
                )
                existing = cur.fetchone()
                if existing is not None:
                    prev = _row_to_entity(existing)
                    detection.id = prev.id
                    detection.created_at = prev.created_at
                    detection.job_id = prev.job_id
                    detection.inventory_id = prev.inventory_id
                    detection.client_id = prev.client_id
                    detection.source_asset_id = prev.source_asset_id
                    cur.execute(
                        """
                        UPDATE dbo.image_position_label_detections
                        SET client_image_id = ?, ordered_capture_session_id = ?,
                            sequence_number = ?, position_label_id = ?, public_identifier = ?,
                            position_name_snapshot = ?, payload_version = ?, signature_status = ?,
                            confidence = ?, bounding_box_json = ?, rotation_degrees = ?,
                            detector_name = ?, metadata_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            detection.client_image_id,
                            detection.ordered_capture_session_id,
                            detection.sequence_number,
                            detection.position_label_id,
                            detection.public_identifier,
                            detection.position_name_snapshot,
                            detection.payload_version,
                            detection.signature_status.value,
                            detection.confidence,
                            _json_dump(detection.bounding_box_json),
                            detection.rotation_degrees,
                            detection.detector_name,
                            _json_dump(detection.metadata_json or None),
                            detection.updated_at,
                            detection.id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO dbo.image_position_label_detections (
                            id, client_id, inventory_id, job_id, source_asset_id, client_image_id,
                            ordered_capture_session_id, sequence_number, position_label_id,
                            public_identifier, position_name_snapshot, payload_version,
                            signature_status, detection_status, confidence, bounding_box_json,
                            rotation_degrees, raw_payload_hash, detector_name, detector_version,
                            metadata_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            detection.id,
                            detection.client_id,
                            detection.inventory_id,
                            detection.job_id,
                            detection.source_asset_id,
                            detection.client_image_id,
                            detection.ordered_capture_session_id,
                            detection.sequence_number,
                            detection.position_label_id,
                            detection.public_identifier,
                            detection.position_name_snapshot,
                            detection.payload_version,
                            detection.signature_status.value,
                            detection.detection_status.value,
                            detection.confidence,
                            _json_dump(detection.bounding_box_json),
                            detection.rotation_degrees,
                            hash_key,
                            detection.detector_name,
                            detection.detector_version,
                            _json_dump(detection.metadata_json or None),
                            detection.created_at,
                            detection.updated_at,
                        ),
                    )
                out.append(detection)
                kept_ids.append(detection.id)

            if kept_ids:
                placeholders = ",".join("?" for _ in kept_ids)
                cur.execute(
                    f"""
                    DELETE FROM dbo.image_position_label_detections
                    WHERE job_id = ? AND source_asset_id = ? AND detector_version = ?
                      AND id NOT IN ({placeholders})
                    """,
                    (job_id, source_asset_id, detector_version, *kept_ids),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM dbo.image_position_label_detections
                    WHERE job_id = ? AND source_asset_id = ? AND detector_version = ?
                    """,
                    (job_id, source_asset_id, detector_version),
                )
            txn.commit()
            return out

    def list_by_job(self, job_id: str) -> list[ImagePositionLabelDetection]:
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT + " WHERE job_id = ? ORDER BY sequence_number ASC, created_at ASC, id ASC",
                (job_id,),
            )
            return [_row_to_entity(r) for r in cur.fetchall()]

    def list_by_asset(
        self, job_id: str, source_asset_id: str
    ) -> list[ImagePositionLabelDetection]:
        with self._client.cursor() as cur:
            cur.execute(
                _SELECT
                + """
                WHERE job_id = ? AND source_asset_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (job_id, source_asset_id),
            )
            return [_row_to_entity(r) for r in cur.fetchall()]
