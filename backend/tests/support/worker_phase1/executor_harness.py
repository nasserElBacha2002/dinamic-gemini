"""Executor harness for worker Phase 1 operational safety tests."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from src.application.ports.clock import Clock
from src.application.ports.repositories import (
    AisleRepository,
    EvidenceRepository,
    InventoryRepository,
    JobRepository,
    PositionRepository,
    ProductRecordRepository,
    RawLabelRepository,
    SourceAssetRepository,
)
from src.application.services.final_count_builder import FinalCountBuilder
from src.application.services.label_normalization import LabelNormalizationService
from src.application.use_cases.pipeline.recompute_consolidated_counts import (
    RecomputeConsolidatedCountsUseCase,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.assets.entities import SourceAsset, SourceAssetType
from src.domain.inventory.entities import Inventory, InventoryProcessingMode, InventoryStatus
from src.domain.jobs.entities import Job, JobStatus
from src.domain.labels.merge import MergeRuleEngine
from src.infrastructure.pipeline.v3_job_executor import RUN_ID, V3JobExecutor
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_evidence_repository import MemoryEvidenceRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_job_repository import MemoryJobRepository
from src.infrastructure.repositories.memory_normalized_label_repository import (
    MemoryNormalizedLabelRepository,
)
from src.infrastructure.repositories.memory_position_repository import MemoryPositionRepository
from src.infrastructure.repositories.memory_product_record_repository import (
    MemoryProductRecordRepository,
)
from src.infrastructure.repositories.memory_raw_label_repository import MemoryRawLabelRepository
from src.infrastructure.repositories.memory_supplier_reference_image_repository import (
    MemorySupplierReferenceImageRepository,
)
from src.pipeline.hybrid_inventory_pipeline import PipelineRunResult


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def make_two_entity_hybrid_report() -> dict[str, Any]:
    return {
        "entities": [
            {
                "entity_uid": "e1",
                "entity_type": "PALLET",
                "internal_code": "SKU-ONE",
                "final_quantity": 2,
                "product_label_quantity": 2,
                "confidence": 0.9,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_0.jpg",
                "source_image_id": "asset-1",
            },
            {
                "entity_uid": "e2",
                "entity_type": "PALLET",
                "internal_code": "SKU-TWO",
                "final_quantity": 4,
                "product_label_quantity": 4,
                "confidence": 0.85,
                "count_status": "COUNTED",
                "evidence_path": "evidence/crop_1.jpg",
                "source_image_id": "asset-2",
            },
        ]
    }


def build_recompute_use_case(
    *,
    raw_repo: RawLabelRepository,
    norm_repo: MemoryNormalizedLabelRepository,
    final_repo: MemoryFinalCountRepository,
    product_repo: ProductRecordRepository,
    position_repo: PositionRepository,
) -> RecomputeConsolidatedCountsUseCase:
    return RecomputeConsolidatedCountsUseCase(
        raw_label_repo=raw_repo,
        normalized_label_repo=norm_repo,
        final_count_repo=final_repo,
        product_record_repo=product_repo,
        position_repo=position_repo,
        normalization_service=LabelNormalizationService(merge_rule_engine=MergeRuleEngine()),
        final_count_builder=FinalCountBuilder(),
    )


@dataclass
class ExecutorHarness:
    """In-memory stack + helpers to run V3JobExecutor with a mocked hybrid pipeline."""

    base_path: Path
    job_id: str
    aisle_id: str
    inventory_id: str
    now: datetime
    job_repo: JobRepository
    aisle_repo: AisleRepository
    inventory_repo: InventoryRepository
    position_repo: PositionRepository
    product_repo: ProductRecordRepository
    evidence_repo: EvidenceRepository
    raw_repo: RawLabelRepository
    norm_repo: MemoryNormalizedLabelRepository
    final_repo: MemoryFinalCountRepository
    source_asset_repo: SourceAssetRepository
    artifact_store: Any = None
    recompute_uc: RecomputeConsolidatedCountsUseCase | None = None
    pipeline_invocations: int = field(default=0, init=False)

    @classmethod
    def build(
        cls,
        tmp_path: Path,
        *,
        job_id: str = "job-phase1",
        aisle_id: str = "aisle-1",
        inventory_id: str = "inv-1",
        job_status: JobStatus = JobStatus.STARTING,
        aisle_status: AisleStatus = AisleStatus.QUEUED,
        processing_mode: InventoryProcessingMode = InventoryProcessingMode.PRODUCTION,
        photo_count: int = 2,
        position_repo: PositionRepository | None = None,
        product_repo: ProductRecordRepository | None = None,
        evidence_repo: EvidenceRepository | None = None,
        raw_repo: RawLabelRepository | None = None,
        norm_repo: MemoryNormalizedLabelRepository | None = None,
        final_repo: MemoryFinalCountRepository | None = None,
        source_asset_repo: SourceAssetRepository | None = None,
        artifact_store: Any | None = None,
        recompute_uc: RecomputeConsolidatedCountsUseCase | None = None,
        job_repo: JobRepository | None = None,
        aisle_repo: AisleRepository | None = None,
        inventory_repo: InventoryRepository | None = None,
    ) -> ExecutorHarness:
        now = datetime(2026, 6, 12, 10, 0, 0, tzinfo=timezone.utc)
        job_repo = job_repo or MemoryJobRepository()
        aisle_repo = aisle_repo or MemoryAisleRepository()
        inventory_repo = inventory_repo or MemoryInventoryRepository()
        position_repo = position_repo or MemoryPositionRepository()
        product_repo = product_repo or MemoryProductRecordRepository()
        evidence_repo = evidence_repo or MemoryEvidenceRepository()
        raw_repo = raw_repo or MemoryRawLabelRepository()
        norm_repo = norm_repo or MemoryNormalizedLabelRepository()
        final_repo = final_repo or MemoryFinalCountRepository()

        if inventory_repo.get_by_id(inventory_id) is None:
            inventory_repo.save(
                Inventory(
                    id=inventory_id,
                    name="Phase1 Inv",
                    status=InventoryStatus.PROCESSING,
                    created_at=now,
                    updated_at=now,
                    processing_mode=processing_mode,
                )
            )
        existing_aisle = aisle_repo.get_by_id(aisle_id)
        if existing_aisle is None:
            aisle_repo.save(
                Aisle(
                    id=aisle_id,
                    inventory_id=inventory_id,
                    code="A01",
                    status=aisle_status,
                    created_at=now,
                    updated_at=now,
                )
            )
        if job_repo.get_by_id(job_id) is None:
            job_repo.save(
                Job(
                    id=job_id,
                    target_type="aisle",
                    target_id=aisle_id,
                    job_type="process_aisle",
                    status=job_status,
                    payload_json={"aisle_id": aisle_id},
                    created_at=now,
                    updated_at=now,
                    execution_id="exec-phase1",
                )
            )

        assets: list[SourceAsset] = []
        v3_base = tmp_path / "v3_uploads" / "photos"
        v3_base.mkdir(parents=True, exist_ok=True)
        for i in range(photo_count):
            asset_id = f"asset-{i + 1}"
            rel = f"photos/{asset_id}.jpg"
            (v3_base / f"{asset_id}.jpg").write_bytes(b"jpeg-bytes")
            assets.append(
                SourceAsset(
                    id=asset_id,
                    aisle_id=aisle_id,
                    type=SourceAssetType.PHOTO,
                    original_filename=f"photo{i + 1}.jpg",
                    storage_path=rel,
                    mime_type="image/jpeg",
                    uploaded_at=now,
                )
            )

        class _AssetRepo:
            def list_by_aisle(self, aid: str) -> Sequence[SourceAsset]:
                return assets if aid == aisle_id else []

        resolved_source_asset_repo = source_asset_repo or _AssetRepo()

        if recompute_uc is None:
            recompute_uc = build_recompute_use_case(
                raw_repo=raw_repo,
                norm_repo=norm_repo,
                final_repo=final_repo,
                product_repo=product_repo,
                position_repo=position_repo,
            )

        return cls(
            base_path=tmp_path,
            job_id=job_id,
            aisle_id=aisle_id,
            inventory_id=inventory_id,
            now=now,
            job_repo=job_repo,
            aisle_repo=aisle_repo,
            inventory_repo=inventory_repo,
            position_repo=position_repo,
            product_repo=product_repo,
            evidence_repo=evidence_repo,
            raw_repo=raw_repo,
            norm_repo=norm_repo,
            final_repo=final_repo,
            source_asset_repo=resolved_source_asset_repo,
            artifact_store=artifact_store,
            recompute_uc=recompute_uc,
        )

    def make_executor(self, **kwargs: Any) -> V3JobExecutor:
        return V3JobExecutor(
            job_repo=kwargs.get("job_repo", self.job_repo),
            aisle_repo=kwargs.get("aisle_repo", self.aisle_repo),
            source_asset_repo=self.source_asset_repo,
            position_repo=kwargs.get("position_repo", self.position_repo),
            product_record_repo=self.product_repo,
            evidence_repo=self.evidence_repo,
            clock=FixedClock(self.now),
            inventory_repo=kwargs.get("inventory_repo", self.inventory_repo),
            supplier_reference_image_repo=MemorySupplierReferenceImageRepository(),
            artifact_store=kwargs.get("artifact_store", self.artifact_store),
            raw_label_repo=self.raw_repo,
            recompute_consolidated_uc=kwargs.get("recompute_uc", self.recompute_uc),
        )

    def seed_run_dir(self, report: dict[str, Any] | None = None) -> Path:
        report = report or make_two_entity_hybrid_report()
        run_dir = self.base_path / self.job_id / RUN_ID
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "hybrid_report.json").write_text(json.dumps(report), encoding="utf-8")
        (run_dir / "execution_log.jsonl").write_text(
            '{"stage":"Pipeline","level":"info","message":"seed"}\n',
            encoding="utf-8",
        )
        (run_dir / "hybrid_report.csv").write_text("col\nval\n", encoding="utf-8")
        return run_dir

    def run_with_mock_pipeline(
        self,
        executor: V3JobExecutor,
        *,
        report: dict[str, Any] | None = None,
        pipeline_side_effect: Any = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> bool:
        self.seed_run_dir(report)
        self.pipeline_invocations = 0

        def _pipeline_side_effect(*_args: Any, **kwargs: Any) -> PipelineRunResult:
            self.pipeline_invocations += 1
            bp = kwargs.get("output_path") or kwargs.get("base_path")
            jid = kwargs.get("video_id") or kwargs.get("job_id") or self.job_id
            if bp is None:
                bp = self.base_path
            run_dir = Path(bp) / str(jid) / RUN_ID
            run_dir.mkdir(parents=True, exist_ok=True)
            payload = report if report is not None else make_two_entity_hybrid_report()
            (run_dir / "hybrid_report.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            return PipelineRunResult(0, run_metadata or {})

        side_effect = pipeline_side_effect or _pipeline_side_effect

        with patch("src.infrastructure.pipeline.v3_job_executor.load_settings") as ms:
            ms.return_value.output_dir = str(self.base_path)
            ms.return_value.artifact_storage_legacy_local_read_enabled = True
            with patch(
                "src.infrastructure.pipeline.v3_job_executor.HybridInventoryPipeline"
            ) as mock_pipeline_cls:
                mock_pipeline_cls.return_value.process_video.side_effect = side_effect
                return executor.execute(self.base_path, self.job_id)

    def positions_for_job(self, job_id: str | None = None) -> list:
        jid = job_id or self.job_id
        return list(self.position_repo.list_by_aisle(self.aisle_id, job_id=jid))

    def execution_log_text(self) -> str:
        path = self.base_path / self.job_id / RUN_ID / "execution_log.jsonl"
        return path.read_text(encoding="utf-8") if path.is_file() else ""
