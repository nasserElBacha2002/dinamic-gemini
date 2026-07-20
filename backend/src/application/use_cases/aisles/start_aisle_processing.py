"""
StartAisleProcessing use case — v3.0 (Épica 4).

Creates a processing job for an aisle and enqueues it. Fails if aisle does not exist,
aisle does not belong to the given inventory, or an active job already exists for the aisle.

Phase 9: when ``resolve_execution_keys`` is true (HTTP entry), loads inventory and resolves
provider/model/prompt via ``resolve_process_aisle_execution_keys`` before launch.

Phase 10: execution-key materialization and aisle scope checks are factored into small helpers
for readability; behavior is unchanged.

Phase 1 (aisle identification): resolves hierarchical identification mode, persists an immutable
job snapshot, and always launches the legacy LLM pipeline (temporary for non-LEGACY modes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.application.errors import (
    ActiveJobExistsError,
    AisleInactiveError,
    InventoryNotFoundError,
    NoSourceAssetsForAisleProcessingError,
)
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    InventoryRepository,
    JobRepository,
    SourceAssetRepository,
)
from src.application.services.aisle_identification_execution import (
    identification_execution_snapshot_dict,
    resolve_execution_strategy_decision,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.image_processing.ocr_client_field_rules import (
    ocr_client_rules_snapshot,
    resolve_ocr_client_field_rules,
)
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.process_aisle_execution_resolution import (
    resolve_process_aisle_execution_keys,
)
from src.config import load_settings
from src.domain.aisle_identification.modes import CONFIGURATION_SNAPSHOT_VERSION
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode
from src.domain.jobs.entities import Job, JobStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

logger = logging.getLogger(__name__)

_START_BLOCKING_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)


def _require_no_active_process_job_for_aisle(
    *,
    stale_reconciler: JobStaleReconciler,
    job_repo: JobRepository,
    aisle_id: str,
) -> None:
    """Raise if an aisle-target job is already in a state that blocks a new start."""
    latest = stale_reconciler.reconcile(job_repo.get_latest_by_target("aisle", aisle_id))
    if latest is not None and latest.status in _START_BLOCKING_JOB_STATUSES:
        raise ActiveJobExistsError(
            f"Aisle {aisle_id} already has an active job (status={latest.status.value})"
        )


@dataclass
class StartAisleProcessingCommand:
    inventory_id: str
    aisle_id: str
    #: When true (API route), load inventory and resolve execution keys from inventory + requests.
    resolve_execution_keys: bool = False
    requested_provider_name: str | None = None
    requested_model_name: str | None = None
    requested_prompt_key: str | None = None
    #: Optional request override for aisle identification mode (job-only; does not mutate aisle).
    requested_identification_mode: str | None = None
    #: Used only when ``resolve_execution_keys`` is false (e.g. unit tests with pre-resolved keys).
    pipeline_provider_key: str = "gemini"
    model_name: str | None = None
    prompt_key: str = DEFAULT_HYBRID_PROMPT_PROFILE
    #: Stable client key; replay returns the existing job for this aisle when found.
    idempotency_key: str | None = None


@dataclass(frozen=True)
class StartAisleProcessingResult:
    job_id: str
    identification_mode: str
    identification_mode_source: str
    execution_strategy: str
    configuration_snapshot_version: int


def _find_job_by_idempotency_key(
    job_repo: JobRepository,
    *,
    aisle_id: str,
    idempotency_key: str | None,
) -> Job | None:
    key = (idempotency_key or "").strip()
    if not key:
        return None
    for job in job_repo.list_jobs_for_target("aisle", aisle_id, limit=100):
        payload = job.payload_json or {}
        if str(payload.get("idempotency_key") or "").strip() == key:
            return job
    return None


def _materialize_execution_keys_for_start(
    inventory_repo: InventoryRepository,
    command: StartAisleProcessingCommand,
):
    """Resolve provider/model/prompt for a start-process command (Phase 9/10).

    When ``command.resolve_execution_keys`` is false, returns the command's pre-set keys.
    """
    if not command.resolve_execution_keys:
        return (
            command.pipeline_provider_key,
            command.model_name,
            command.prompt_key,
            None,
        )
    inv = inventory_repo.get_by_id(command.inventory_id)
    if inv is None:
        raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")
    settings = load_settings()
    pipeline_key, model_name, prompt_key = resolve_process_aisle_execution_keys(
        inv,
        requested_provider_name=command.requested_provider_name,
        requested_model_name=command.requested_model_name,
        requested_prompt_key=command.requested_prompt_key,
        settings=settings,
    )
    logger.info(
        "aisle.process_requested inventory_id=%s aisle_id=%s processing_mode=%s provider=%s",
        command.inventory_id,
        command.aisle_id,
        inv.processing_mode.value,
        pipeline_key,
    )
    return pipeline_key, model_name, prompt_key, inv


class StartAisleProcessingUseCase:
    def __init__(
        self,
        inventory_repo: InventoryRepository,
        aisle_repo: AisleRepository,
        asset_repo: SourceAssetRepository,
        job_repo: JobRepository,
        launch_service: AisleJobLaunchService,
        stale_reconciler: JobStaleReconciler,
        client_repo: ClientRepository | None = None,
        extraction_profile_repo=None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler
        self._client_repo = client_repo
        self._extraction_profile_repo = extraction_profile_repo

    def execute(self, command: StartAisleProcessingCommand) -> StartAisleProcessingResult:
        pipeline_key, model_name, _resolved_prompt, inv_from_keys = (
            _materialize_execution_keys_for_start(
                self._inventory_repo,
                command,
            )
        )
        # Product policy: all new aisle jobs persist the label-first hybrid profile key.
        prompt_key = DEFAULT_HYBRID_PROMPT_PROFILE
        aisle = require_aisle_scoped_to_inventory(
            self._aisle_repo,
            inventory_id=command.inventory_id,
            aisle_id=command.aisle_id,
            detail_style="strict",
        )
        if not aisle.is_active:
            raise AisleInactiveError(
                f"Aisle {command.aisle_id} is inactive; reactivate before processing."
            )

        aisle_assets = self._asset_repo.list_by_aisle(command.aisle_id)
        if not aisle_assets:
            logger.info(
                "aisle.process_rejected_no_source_assets inventory_id=%s aisle_id=%s",
                command.inventory_id,
                command.aisle_id,
            )
            raise NoSourceAssetsForAisleProcessingError(
                f"No source assets for aisle {command.aisle_id}; upload media before processing."
            )

        existing_idempotent = _find_job_by_idempotency_key(
            self._job_repo,
            aisle_id=command.aisle_id,
            idempotency_key=command.idempotency_key,
        )
        if existing_idempotent is not None:
            logger.info(
                "aisle.process_idempotent_replay inventory_id=%s aisle_id=%s job_id=%s",
                command.inventory_id,
                command.aisle_id,
                existing_idempotent.id,
            )
            return StartAisleProcessingResult(
                job_id=existing_idempotent.id,
                identification_mode=existing_idempotent.identification_mode.value,
                identification_mode_source=existing_idempotent.identification_mode_source.value,
                execution_strategy=existing_idempotent.execution_strategy.value,
                configuration_snapshot_version=existing_idempotent.configuration_snapshot_version,
            )

        _require_no_active_process_job_for_aisle(
            stale_reconciler=self._stale_reconciler,
            job_repo=self._job_repo,
            aisle_id=command.aisle_id,
        )

        inventory = inv_from_keys or self._inventory_repo.get_by_id(command.inventory_id)
        if inventory is None:
            raise InventoryNotFoundError(f"Inventory not found: {command.inventory_id}")

        client_mode = None
        if inventory.client_id and self._client_repo is not None:
            client = self._client_repo.get_by_id(inventory.client_id)
            if client is not None and client.default_identification_mode is not None:
                client_mode = client.default_identification_mode

        settings = load_settings()
        resolution = resolve_aisle_identification_mode(
            request_mode=command.requested_identification_mode,
            aisle_mode=aisle.identification_mode,
            inventory_mode=inventory.identification_mode,
            client_mode=client_mode,
        )
        decision = resolve_execution_strategy_decision(
            effective_mode=resolution.effective_mode,
            pipeline_enabled=bool(settings.aisle_identification_pipeline_enabled),
            code_scan_processing_enabled=bool(
                getattr(settings, "code_scan_processing_enabled", False)
            ),
            internal_ocr_processing_enabled=bool(
                getattr(settings, "internal_ocr_processing_enabled", False)
            ),
        )
        execution_strategy = decision.strategy

        client_id = inventory.client_id
        client_rules = resolve_ocr_client_field_rules(
            client_id=client_id,
            ean_first_client_ids=getattr(settings, "internal_ocr_ean_first_client_ids", ""),
            global_prefer_ean=bool(
                getattr(settings, "internal_ocr_prefer_ean_as_internal_code", False)
            ),
        )
        supplier_id = getattr(aisle, "client_supplier_id", None)
        supplier_extraction_profile = None
        profiles_enabled = bool(
            getattr(settings, "client_extraction_profiles_enabled", False)
        )
        profile_aware = bool(
            getattr(settings, "profile_aware_validation_enabled", False)
        )
        annotations_enabled = bool(
            getattr(settings, "reference_template_annotations_enabled", False)
        )
        if profiles_enabled or profile_aware:
            from src.application.services.image_processing.extraction_profile_configuration import (
                ExtractionProfileConfigurationError,
                parse_extraction_configuration,
            )
            from src.application.services.image_processing.profile_aware_processing_result_validator import (
                configuration_to_ocr_client_field_rules,
            )
            from src.application.services.image_processing.supplier_extraction_profile_resolver import (
                SupplierExtractionProfileResolver,
            )

            resolver = SupplierExtractionProfileResolver(
                self._extraction_profile_repo,
                profiles_enabled=bool(profiles_enabled or profile_aware),
            )
            supplier_extraction_profile = resolver.build_snapshot_for_new_job(
                client_id=client_id,
                supplier_id=str(supplier_id).strip() if supplier_id else None,
            ) or None
            if profile_aware and isinstance(supplier_extraction_profile, dict):
                try:
                    cfg = parse_extraction_configuration(
                        supplier_extraction_profile.get("configuration")
                    )
                    client_rules = configuration_to_ocr_client_field_rules(cfg)
                except ExtractionProfileConfigurationError as exc:
                    raise ValueError(
                        f"PROFILE_SNAPSHOT_INVALID: cannot start job with invalid "
                        f"extraction profile: {exc.message}"
                    ) from exc
        ocr_config = None
        if (
            resolution.effective_mode.value == "INTERNAL_OCR"
            or execution_strategy.value == "INTERNAL_OCR"
        ):
            ocr_config = {
                "engine": getattr(settings, "internal_ocr_engine", "tesseract"),
                "language": getattr(settings, "internal_ocr_language", "spa+eng"),
                "max_variants": getattr(settings, "internal_ocr_max_variants", 3),
                "timeout_seconds": getattr(settings, "internal_ocr_timeout_seconds", 20),
                "max_image_dimension": getattr(
                    settings, "internal_ocr_max_image_dimension", 2048
                ),
                "enable_deskew": getattr(settings, "internal_ocr_enable_deskew", False),
                "quantity_max": getattr(settings, "internal_ocr_quantity_max", 99999999),
                "min_aggregate_confidence": getattr(
                    settings, "internal_ocr_min_aggregate_confidence", None
                ),
                "processor_version": "1.0.0",
                "label_detection_enabled": bool(
                    getattr(settings, "ocr_label_detection_enabled", False)
                ),
                "diagnostic_evidence_enabled": bool(
                    getattr(settings, "ocr_diagnostic_evidence_enabled", False)
                ),
                "page_segmentation_modes": [6, 11, 12],
                "light_ocr_timeout_seconds": 3.0,
                "max_light_ocr_candidates": 3,
                "variant_plan_version": "v1",
                "label_detection_rules": (
                    (
                        supplier_extraction_profile.get("configuration") or {}
                    ).get("label_detection_rules")
                    if isinstance(supplier_extraction_profile, dict)
                    else None
                ),
            }
        from src.application.services.image_processing.external_provider_fallback_orchestrator import (
            build_external_fallback_snapshot_dict,
        )
        from src.application.services.image_processing.fallback_eligibility_policy import (
            DEFAULT_RECOVERABLE_TECHNICAL_CODES,
        )

        external_fallback = None
        if execution_strategy.value in ("CODE_SCAN", "INTERNAL_OCR"):
            if bool(getattr(settings, "multi_provider_fallback_enabled", False)):
                raise ValueError(
                    "MULTI_PROVIDER_FALLBACK_ENABLED is not supported in Phase 5; "
                    "keep it false and use a single EXTERNAL_FALLBACK_PROVIDER."
                )
            fallback_enabled = bool(
                getattr(settings, "external_fallback_per_image_enabled", False)
            )
            provider_key = str(
                getattr(settings, "external_fallback_provider", "gemini") or "gemini"
            ).strip().lower()
            if fallback_enabled:
                from src.pipeline.providers.registry import (
                    UnknownPipelineProviderError,
                    resolve_llm_executor,
                )

                try:
                    resolve_llm_executor(provider_key, settings)
                except UnknownPipelineProviderError as exc:
                    raise ValueError(
                        f"EXTERNAL_FALLBACK_PROVIDER={provider_key!r} is not a registered "
                        f"pipeline provider: {exc}"
                    ) from exc
            external_fallback = build_external_fallback_snapshot_dict(
                enabled=fallback_enabled,
                provider=provider_key,
                model=(
                    str(getattr(settings, "external_fallback_model", "") or "").strip()
                    or None
                ),
                timeout_seconds=float(
                    getattr(settings, "external_fallback_timeout_seconds", 60)
                ),
                max_attempts=int(getattr(settings, "external_fallback_max_attempts", 1)),
                max_concurrency=int(
                    getattr(settings, "max_external_fallback_concurrency", 1)
                ),
                max_image_dimension=int(
                    getattr(settings, "external_fallback_max_image_dimension", 2048)
                ),
                quantity_max=int(
                    getattr(settings, "code_scan_quantity_max", 99_999_999)
                    if execution_strategy.value == "CODE_SCAN"
                    else getattr(settings, "internal_ocr_quantity_max", 99_999_999)
                ),
                circuit_breaker_threshold=int(
                    getattr(settings, "external_fallback_circuit_breaker_threshold", 5)
                ),
                circuit_breaker_cooldown_seconds=float(
                    getattr(
                        settings,
                        "external_fallback_circuit_breaker_cooldown_seconds",
                        60,
                    )
                ),
                multi_provider_enabled=False,
                snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
                client_rules=ocr_client_rules_snapshot(client_rules),
                recoverable_technical_codes=sorted(DEFAULT_RECOVERABLE_TECHNICAL_CODES),
            )
        engine_params_json = {
            "identification_execution": identification_execution_snapshot_dict(
                decision,
                ocr_config=ocr_config,
                client_rules=ocr_client_rules_snapshot(client_rules),
                configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
                external_fallback=external_fallback,
                supplier_extraction_profile=supplier_extraction_profile,
                client_extraction_profiles_enabled=profiles_enabled,
                profile_aware_validation_enabled=profile_aware,
                reference_template_annotations_enabled=annotations_enabled,
                profile_snapshotted=bool(supplier_extraction_profile),
                profile_validation_executed=False,
            ),
            "client_id": client_id,
            "supplier_id": str(supplier_id).strip() if supplier_id else None,
        }

        logger.info(
            "aisle.identification_resolved inventory_id=%s aisle_id=%s "
            "requested_identification_mode=%s configured_aisle=%s configured_inventory=%s "
            "configured_client=%s effective_identification_mode=%s identification_mode_source=%s "
            "configuration_snapshot_version=%s aisle_identification_pipeline_enabled=%s "
            "actual_execution_strategy=%s execution_reason=%s",
            command.inventory_id,
            command.aisle_id,
            command.requested_identification_mode,
            aisle.identification_mode.value if aisle.identification_mode else None,
            inventory.identification_mode.value if inventory.identification_mode else None,
            client_mode.value if client_mode else None,
            resolution.effective_mode.value,
            resolution.source.value,
            CONFIGURATION_SNAPSHOT_VERSION,
            settings.aisle_identification_pipeline_enabled,
            execution_strategy.value,
            decision.reason,
        )

        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        if command.idempotency_key and str(command.idempotency_key).strip():
            payload["idempotency_key"] = str(command.idempotency_key).strip()
        job = self._launch_service.create_and_launch_attempt(
            aisle=aisle,
            payload=payload,
            attempt_count=1,
            retry_of_job_id=None,
            log_prefix="job.start_requested",
            provider_name=pipeline_key,
            model_name=model_name,
            prompt_key=prompt_key,
            identification_mode=resolution.effective_mode,
            identification_mode_source=resolution.source,
            configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
            execution_strategy=execution_strategy,
            engine_params_json=engine_params_json,
        )
        return StartAisleProcessingResult(
            job_id=job.id,
            identification_mode=job.identification_mode.value,
            identification_mode_source=job.identification_mode_source.value,
            execution_strategy=job.execution_strategy.value,
            configuration_snapshot_version=job.configuration_snapshot_version,
        )
