"""Summary grouping rules for aisle code scans."""

from __future__ import annotations

from src.domain.code_scans.entities import CodeScanDetectionStatus


def detection_counts_toward_summary(status: CodeScanDetectionStatus) -> bool:
    """Phase 1: summary counts useful detections only (excludes duplicate/error/low_confidence)."""
    return status == CodeScanDetectionStatus.DETECTED
