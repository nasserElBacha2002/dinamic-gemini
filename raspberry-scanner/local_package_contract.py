"""Constants aligned with mobile ``localPackageContract`` / ``csvFormat``."""

from __future__ import annotations

PACKAGE_KIND = "DINAMIC_LOCAL_AISLE_EXPORT"
PACKAGE_VERSION = 2
LOCAL_CSV_SCHEMA_VERSION = "1.1"
CHECKSUM_ALGORITHM = "sha256"

LOCAL_CSV_HEADERS: tuple[str, ...] = (
    "schema_version",
    "export_id",
    "exported_at",
    "device_id",
    "inventory_id",
    "aisle_id",
    "capture_session_id",
    "capture_photo_id",
    "client_file_id",
    "capture_order",
    "captured_at",
    "position_code",
    "position_label_id",
    "position_payload_raw",
    "internal_code",
    "label_id",
    "quantity",
    "quantity_status",
    "detection_status",
    "source",
    "requires_review",
    "error_code",
    "notes",
)
