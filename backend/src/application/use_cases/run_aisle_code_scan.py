"""Run a synchronous aisle code scan (Phase 2: pyzbar scanner + storage reads)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from src.application.errors import (
    CodeScanDisabledError,
    CodeScanMaxAssetsExceededError,
    NoSourceAssetsForCodeScanError,
)
from src.application.ports.clock import Clock
from src.application.ports.code_scan_repository import CodeScanRepository
from src.application.ports.code_scanner import CodeScannerPort
from src.application.ports.repositories import AisleRepository, SourceAssetRepository
from src.application.ports.source_asset_content_reader import SourceAssetContentReader
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.code_scan_normalization import (
    code_value_within_limit,
    normalize_code_value,
)
from src.application.services.code_scan_run_metadata import (
    build_run_metadata,
    skipped_asset_entry,
)
from src.config import load_settings
from src.domain.assets.entities import SourceAssetType
from src.domain.code_scans.bounding_box import parse_bounding_box
from src.domain.code_scans.entities import (
    CodeScanDetection,
    CodeScanDetectionStatus,
    CodeScanRun,
    CodeScanRunStatus,
    CodeType,
)
from src.infrastructure.code_scanning.image_decode import (
    UnreadableImageError,
    UnsupportedImageFormatError,
    is_supported_image_asset,
)

logger = logging.getLogger(__name__)

_SCANNABLE_TYPES = {SourceAssetType.PHOTO}


@dataclass(frozen=True)
class RunAisleCodeScanCommand:
    inventory_id: str
    aisle_id: str
    created_by: str | None = None


@dataclass(frozen=True)
class RunAisleCodeScanResult:
    run_id: str
    status: CodeScanRunStatus
    total_assets: int
    processed_assets: int
    failed_assets: int
    total_codes_found: int
    total_qr_found: int
    total_barcodes_found: int
    warnings: tuple[str, ...]
    started_at: Any
    finished_at: Any
    scanner_engine: str
    error_message: str | None = None


class RunAisleCodeScanUseCase:
    def __init__(
        self,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        code_scan_repo: CodeScanRepository,
        scanner: CodeScannerPort,
        content_reader: SourceAssetContentReader,
        clock: Clock,
    ) -> None:
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._code_scan_repo = code_scan_repo
        self._scanner = scanner
        self._content_reader = content_reader
        self._clock = clock

    def execute(self, command: RunAisleCodeScanCommand) -> RunAisleCodeScanResult:
        settings = load_settings()
        if not settings.code_scan_enabled:
            raise CodeScanDisabledError("Aisle code scan is disabled by configuration")

        require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )

        assets = list(self._asset_repo.list_by_aisle(command.aisle_id))
        if not assets:
            raise NoSourceAssetsForCodeScanError(
                f"No source assets for aisle {command.aisle_id}; upload media before scanning."
            )

        max_assets = settings.code_scan_max_assets_per_run
        if len(assets) > max_assets:
            raise CodeScanMaxAssetsExceededError(
                f"At most {max_assets} assets allowed per code scan run; aisle has {len(assets)}."
            )

        max_payload = settings.code_scan_max_decoded_payload_length
        now = self._clock.now()
        run_id = str(uuid4())
        warnings: list[str] = []
        skipped_assets: list[dict[str, Any]] = []
        scanner_errors: list[str] = []
        unreadable_assets: list[dict[str, Any]] = []
        unsupported_assets: list[dict[str, Any]] = []

        run = CodeScanRun(
            id=run_id,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            status=CodeScanRunStatus.RUNNING,
            total_assets=len(assets),
            processed_assets=0,
            failed_assets=0,
            total_codes_found=0,
            total_qr_found=0,
            total_barcodes_found=0,
            started_at=now,
            finished_at=None,
            scanner_engine=self._scanner.engine_name,
            is_latest=True,
            created_by=command.created_by,
            metadata_json=build_run_metadata(),
        )
        self._code_scan_repo.replace_latest_run(run)

        detections: list[CodeScanDetection] = []
        processed = 0
        failed = 0
        total_codes = 0
        total_qr = 0
        total_barcodes = 0

        try:
            for asset in assets:
                if asset.type not in _SCANNABLE_TYPES:
                    failed += 1
                    entry = skipped_asset_entry(
                        asset_id=asset.id,
                        reason="unsupported_asset_type",
                        asset_type=asset.type.value,
                    )
                    skipped_assets.append(entry)
                    unsupported_assets.append(entry)
                    warnings.append(
                        f"Skipped unsupported asset type {asset.type.value} for asset {asset.id}"
                    )
                    continue

                if not is_supported_image_asset(asset):
                    failed += 1
                    entry = skipped_asset_entry(
                        asset_id=asset.id,
                        reason="unsupported_image_format",
                    )
                    skipped_assets.append(entry)
                    unsupported_assets.append(entry)
                    warnings.append(
                        f"Skipped unsupported image format for asset {asset.id}"
                    )
                    continue

                try:
                    content = self._content_reader.read_image_bytes(asset)
                except (FileNotFoundError, ValueError) as exc:
                    failed += 1
                    scanner_errors.append(f"{asset.id}: storage_read")
                    unreadable_assets.append(
                        skipped_asset_entry(asset_id=asset.id, reason="storage_read_failed")
                    )
                    warnings.append(f"Could not read asset {asset.id} from storage")
                    logger.warning(
                        "code_scan storage_read_failed aisle_id=%s asset_id=%s error=%s",
                        command.aisle_id,
                        asset.id,
                        type(exc).__name__,
                    )
                    continue

                try:
                    candidates = self._scanner.scan_asset(asset, content=content)
                except UnsupportedImageFormatError:
                    failed += 1
                    entry = skipped_asset_entry(
                        asset_id=asset.id,
                        reason="unsupported_image_format",
                    )
                    skipped_assets.append(entry)
                    unsupported_assets.append(entry)
                    warnings.append(f"Unsupported image format for asset {asset.id}")
                    continue
                except UnreadableImageError:
                    failed += 1
                    entry = skipped_asset_entry(
                        asset_id=asset.id,
                        reason="unreadable_image",
                    )
                    skipped_assets.append(entry)
                    unreadable_assets.append(entry)
                    warnings.append(f"Unreadable image for asset {asset.id}")
                    continue
                except Exception as exc:
                    failed += 1
                    scanner_errors.append(f"{asset.id}: {type(exc).__name__}")
                    unreadable_assets.append(
                        skipped_asset_entry(asset_id=asset.id, reason="scanner_failed")
                    )
                    warnings.append(f"Scanner failed for asset {asset.id}")
                    logger.warning(
                        "code_scan asset_failed aisle_id=%s asset_id=%s error=%s",
                        command.aisle_id,
                        asset.id,
                        type(exc).__name__,
                    )
                    continue

                processed += 1
                seen_on_asset: set[tuple[str, str]] = set()
                for cand in candidates:
                    raw_value = cand.code_value or ""
                    normalized = normalize_code_value(raw_value)
                    if not normalized:
                        warnings.append(f"Empty code value skipped for asset {asset.id}")
                        continue
                    if not code_value_within_limit(normalized, max_payload):
                        warnings.append(
                            f"Code value exceeds max length for asset {asset.id}; detection skipped"
                        )
                        continue

                    dedupe_key = (normalized, cand.code_type.value)
                    status = cand.detection_status
                    if dedupe_key in seen_on_asset:
                        status = CodeScanDetectionStatus.DUPLICATE
                    else:
                        seen_on_asset.add(dedupe_key)

                    if status == CodeScanDetectionStatus.DETECTED:
                        total_codes += 1
                        if cand.code_type == CodeType.QR:
                            total_qr += 1
                        elif cand.code_type == CodeType.BARCODE:
                            total_barcodes += 1

                    bbox = parse_bounding_box(cand.bounding_box_json)

                    detections.append(
                        CodeScanDetection(
                            id=str(uuid4()),
                            run_id=run_id,
                            inventory_id=command.inventory_id,
                            aisle_id=command.aisle_id,
                            asset_id=asset.id,
                            code_type=cand.code_type,
                            code_value=raw_value,
                            normalized_code_value=normalized,
                            detection_status=status,
                            scanner_engine=self._scanner.engine_name,
                            created_at=now,
                            bounding_box_json=bbox,
                            confidence=cand.confidence,
                            metadata_json=cand.metadata_json,
                        )
                    )

            if detections:
                self._code_scan_repo.save_detections(detections)

            finished = self._clock.now()
            if failed > 0 or warnings:
                final_status = CodeScanRunStatus.COMPLETED_WITH_WARNINGS
            else:
                final_status = CodeScanRunStatus.COMPLETED

            run.status = final_status
            run.processed_assets = processed
            run.failed_assets = failed
            run.total_codes_found = total_codes
            run.total_qr_found = total_qr
            run.total_barcodes_found = total_barcodes
            run.finished_at = finished
            run.metadata_json = build_run_metadata(
                warnings=warnings,
                skipped_assets=skipped_assets,
                scanner_errors=scanner_errors,
                unreadable_assets=unreadable_assets,
                unsupported_assets=unsupported_assets,
            )
            self._code_scan_repo.save_run(run)

            return RunAisleCodeScanResult(
                run_id=run_id,
                status=final_status,
                total_assets=run.total_assets,
                processed_assets=processed,
                failed_assets=failed,
                total_codes_found=total_codes,
                total_qr_found=total_qr,
                total_barcodes_found=total_barcodes,
                warnings=tuple(warnings),
                started_at=now,
                finished_at=finished,
                scanner_engine=self._scanner.engine_name,
                error_message=None,
            )
        except Exception as exc:
            finished = self._clock.now()
            run.status = CodeScanRunStatus.FAILED
            run.finished_at = finished
            run.error_message = str(exc)
            run.metadata_json = build_run_metadata(
                warnings=warnings,
                skipped_assets=skipped_assets,
                scanner_errors=scanner_errors + [str(exc)],
                unreadable_assets=unreadable_assets,
                unsupported_assets=unsupported_assets,
            )
            try:
                self._code_scan_repo.save_run(run)
            except Exception:
                logger.exception(
                    "code_scan failed to persist failed run state run_id=%s",
                    run_id,
                )
            logger.exception(
                "code_scan run_failed inventory_id=%s aisle_id=%s run_id=%s",
                command.inventory_id,
                command.aisle_id,
                run_id,
            )
            raise
