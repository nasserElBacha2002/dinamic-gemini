"""Allowed detection sources from mobile CSV vs server ingestion channel."""

from __future__ import annotations

# Channel assigned by the server — never trusted from the client CSV.
INGESTION_SOURCE_LOCAL_CSV_IMPORT = "LOCAL_CSV_IMPORT"

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
