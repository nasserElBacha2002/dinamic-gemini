"""Allowed detection sources from mobile CSV vs server ingestion channel."""

from __future__ import annotations

from typing import Final, Literal

IngestionSource = Literal["LOCAL_CSV_IMPORT", "DINAMIC_SCANNER_TXT"]

# Channel assigned by the server — never trusted from the client CSV.
INGESTION_SOURCE_LOCAL_CSV_IMPORT: Final[IngestionSource] = "LOCAL_CSV_IMPORT"
INGESTION_SOURCE_DINAMIC_SCANNER_TXT: Final[IngestionSource] = "DINAMIC_SCANNER_TXT"

ALLOWED_INGESTION_SOURCES = frozenset(
    {
        INGESTION_SOURCE_LOCAL_CSV_IMPORT,
        INGESTION_SOURCE_DINAMIC_SCANNER_TXT,
    }
)

# Common detection source for Dinamic Scanner D1 product records.
LOCAL_CODE_SCAN_DETECTION_SOURCE = "LOCAL_CODE_SCAN"

# Detection provenance written by the mobile exporter into the `source` column.
ALLOWED_DETECTION_SOURCES = frozenset(
    {
        "LOCAL_PENDING",
        "LOCAL_CODE_SCAN",
        "LOCAL_MANUAL",
        "LOCAL_MANUAL_CORRECTION",
        "LOCAL_POSITION_LABEL",
        "LOCAL_CODE_SCAN_SHADOW",
    }
)

# Backward-compatible: older fixtures may still emit this in `source`.
LEGACY_SOURCE_AS_DETECTION = frozenset({INGESTION_SOURCE_LOCAL_CSV_IMPORT})
