"""Proposal sink — captures remote strategy outputs without writing positions."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.image_processing.contracts import ImageProcessingResult, ImageResultStatus
from src.domain.server_reprocess.entities import RemoteProposalInput


@dataclass
class ServerReprocessProposalResultSink:
    """Collects per-asset strategy results for proposal building (never persists positions)."""

    results: list[RemoteProposalInput] = field(default_factory=list)

    def accept(self, result: ImageProcessingResult) -> None:
        status = result.status
        resolved = status in (
            ImageResultStatus.RESOLVED_INTERNAL,
            ImageResultStatus.RESOLVED_EXTERNAL,
        )
        ambiguous = status is ImageResultStatus.PENDING_MANUAL_REVIEW
        comparable = status is not ImageResultStatus.FAILED_TECHNICAL
        # GLOBAL_BATCH without per-asset mapping must be flagged by caller via metadata.
        meta = getattr(result, "additional_fields", None) or {}
        global_unmapped = bool(
            isinstance(meta, dict) and meta.get("global_batch_unmapped") is True
        )
        self.results.append(
            RemoteProposalInput(
                asset_id=result.asset_id,
                remote_result_id=None,
                internal_code=(result.internal_code or None),
                quantity=float(result.quantity) if result.quantity is not None else None,
                confidence=None,
                source=result.resolved_by or result.processing_mode,
                pipeline_version=None,
                resolved=bool(resolved and (result.internal_code or "").strip()),
                ambiguous=ambiguous,
                comparable=comparable and not global_unmapped,
                global_batch_unmapped=global_unmapped,
            )
        )

    def as_remote_inputs(self) -> list[RemoteProposalInput]:
        return list(self.results)
