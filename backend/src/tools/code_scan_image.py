"""Dev CLI: scan a local image through the real CODE_SCAN path (no DB persist).

Usage:
  cd backend && .venv/bin/python -m src.tools.code_scan_image path/to/photo.jpg
  .venv/bin/python -m src.tools.code_scan_image photo1.jpg photo2.jpg --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.application.services.image_processing.code_detection_consolidator import (
    CodeDetectionConsolidator,
)
from src.application.services.image_processing.code_scan_processing_strategy import (
    CodeScanConfig,
    CodeScanProcessingStrategy,
)
from src.application.services.image_processing.encoded_label_payload_parser import (
    EncodedLabelPayloadParser,
)
from src.domain.aisle_identification.modes import (
    CONFIGURATION_SNAPSHOT_VERSION,
    AisleIdentificationExecutionStrategy,
    AisleIdentificationMode,
)
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.image_processing.contracts import ExecutionScope, ImageProcessingContext
from src.domain.product_labels.format import parse_product_label_payload


class _BytesReader:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read_image_bytes(self, asset: SourceAsset) -> bytes:
        return self._content


def _strategy(content: bytes, *, timeout_seconds: int) -> CodeScanProcessingStrategy:
    from src.infrastructure.code_scanning.pyzbar_code_scanner import PyzbarCodeScanner

    return CodeScanProcessingStrategy(
        scanner=PyzbarCodeScanner(),
        content_reader=_BytesReader(content),
        parser=EncodedLabelPayloadParser(quantity_max=99999999, allow_decimal_quantity=False),
        consolidator=CodeDetectionConsolidator(),
        config=CodeScanConfig(
            quantity_max=99999999,
            timeout_seconds=timeout_seconds,
            enable_rotations=True,
            max_variants=4,
            max_candidates_per_asset=24,
        ),
    )


def _asset(path: Path) -> SourceAsset:
    now = datetime.now(timezone.utc)
    suffix = path.suffix.lower()
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return SourceAsset(
        id=f"scan-{path.stem}",
        aisle_id="diag",
        type=SourceAssetType.PHOTO,
        original_filename=path.name,
        storage_path=str(path),
        mime_type=mime,
        uploaded_at=now,
    )


def _context(asset_id: str) -> ImageProcessingContext:
    return ImageProcessingContext(
        job_id="diag-scan",
        asset_id=asset_id,
        aisle_id="diag",
        inventory_id="diag",
        client_id=None,
        identification_mode=AisleIdentificationMode.CODE_SCAN,
        execution_strategy=AisleIdentificationExecutionStrategy.CODE_SCAN,
        configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
        provider_name="code_scan",
        model_name="pyzbar",
        prompt_key=None,
        prompt_version=None,
        attempt_number=1,
        execution_scope=ExecutionScope.SINGLE_ASSET,
    )


def diagnose_path(path: Path, *, timeout_seconds: int) -> dict:
    content = path.read_bytes()
    strategy = _strategy(content, timeout_seconds=timeout_seconds)
    asset = _asset(path)
    session = strategy._scan_with_variants(asset, content, started=__import__("time").monotonic())
    result = strategy.process(_context(asset.id), asset)

    d1_accepted = []
    d1_rejected = []
    for cand in session.candidates:
        raw = cand.code_value or ""
        parsed = parse_product_label_payload(raw)
        if parsed.status.value == "NOT_OUR_FORMAT":
            continue
        entry = {
            "label_id": parsed.label_id,
            "status": parsed.status.value,
            "internal_code": parsed.internal_code,
            "quantity": parsed.quantity,
        }
        if parsed.status.value == "VALID":
            d1_accepted.append(entry)
        else:
            d1_rejected.append(entry)

    return {
        "file": str(path),
        "bytes": len(content),
        "original_width": session.original_width,
        "original_height": session.original_height,
        "processed_width": session.processed_width,
        "processed_height": session.processed_height,
        "scale_ratio": session.scale_ratio,
        "scan_complete": session.scan_complete,
        "stop_reason": session.stop_reason.value,
        "variants_attempted": session.variants_attempted,
        "variants": [
            {
                "type": o.variant_type,
                "angle": o.rotation_angle,
                "symbols": o.symbols_detected_count,
                "merged": o.candidate_count_after_merge,
                "duration_ms": o.duration_ms,
            }
            for o in session.variant_observations
        ],
        "raw_symbols": len(session.candidates),
        "d1_accepted": d1_accepted,
        "d1_rejected": d1_rejected,
        "result_status": getattr(result.status, "value", str(result.status)),
        "result_warnings": list(result.warnings or []),
        "product_results": [
            {
                "label_id": getattr(p, "label_id", None),
                "internal_code": getattr(p, "internal_code", None),
                "quantity": getattr(p, "quantity", None),
            }
            for p in (result.product_results or [])
        ],
        "evidence": {
            k: (result.evidence or {}).get(k)
            for k in (
                "scan_complete",
                "scan_stop_reason",
                "raw_symbols_count",
                "valid_product_count",
                "rejected_product_count",
            )
        },
    }


def _print_human(report: dict) -> None:
    print(f"\n=== {report['file']} ===")
    print(
        f"dims original={report['original_width']}x{report['original_height']} "
        f"processed={report['processed_width']}x{report['processed_height']} "
        f"scale={report['scale_ratio']}"
    )
    print(
        f"scan_complete={report['scan_complete']} stop_reason={report['stop_reason']} "
        f"variants={report['variants_attempted']} raw_symbols={report['raw_symbols']}"
    )
    for v in report["variants"]:
        print(
            f"  variant {v['type']} angle={v['angle']}: "
            f"symbols={v['symbols']} merged={v['merged']} duration_ms={v['duration_ms']}"
        )
    print(f"D1 accepted ({len(report['d1_accepted'])}):")
    for row in report["d1_accepted"]:
        print(f"  {row}")
    print(f"D1 rejected ({len(report['d1_rejected'])}):")
    for row in report["d1_rejected"]:
        print(f"  {row}")
    print(f"result_status={report['result_status']} warnings={report['result_warnings']}")
    print(f"product_results={report['product_results']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose CODE_SCAN on local image files")
    parser.add_argument("images", nargs="+", type=Path, help="JPG/PNG paths")
    parser.add_argument("--json", action="store_true", help="Emit JSON array")
    parser.add_argument("--timeout", type=int, default=15, help="Variants budget seconds")
    args = parser.parse_args(argv)

    reports = []
    for path in args.images:
        if not path.is_file():
            print(f"missing file: {path}", file=sys.stderr)
            return 2
        reports.append(diagnose_path(path, timeout_seconds=args.timeout))

    if args.json:
        print(json.dumps(reports, indent=2, default=str))
    else:
        for report in reports:
            _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
