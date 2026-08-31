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

from src.application.dto.access_principal import AccessPrincipal
from src.application.errors import (
    ActiveJobExistsError,
    AisleInactiveError,
    InventoryNotFoundError,
    NoSourceAssetsForAisleProcessingError,
    ProcessingRejectedUnsealedSessionError,
)
from src.application.ports.client_supplier_label_profile_repository import (
    ClientSupplierLabelProfileRepository,
)
from src.application.ports.contracts import ProcessAislePayload
from src.application.ports.ordered_capture_session_repository import (
    OrderedCaptureSessionRepository,
)
from src.application.ports.repositories import (
    AisleRepository,
    ClientRepository,
    ClientSupplierRepository,
    InventoryRepository,
    JobRepository,
    SourceAssetRepository,
    SupplierPromptConfigRepository,
)
from src.application.services.aisle_identification_execution import (
    identification_execution_snapshot_dict,
    resolve_execution_strategy_decision,
)
from src.application.services.aisle_inventory_scope import require_aisle_scoped_to_inventory
from src.application.services.aisle_job_launch_service import AisleJobLaunchService
from src.application.services.capture_sequence import (
    sort_assets_by_logical_sequence,
    validate_complete_sequence,
)
from src.application.services.image_processing.ocr_client_field_rules import (
    ocr_client_rules_snapshot,
    resolve_ocr_client_field_rules,
)
from src.application.services.inventory_access_policy import InventoryAccessPolicy
from src.application.services.job_stale_reconciler import JobStaleReconciler
from src.application.services.label_profile_resolver import (
    LabelProfileResolutionContext,
    LabelProfileResolver,
)
from src.application.services.legacy_processing_guard import (
    reject_legacy_effective_mode_for_new_job,
)
from src.application.services.ordered_capture_processing_reservation import (
    OrderedCaptureProcessingReservationService,
)
from src.application.services.process_aisle_execution_resolution import (
    resolve_process_aisle_execution_keys,
)
from src.config import load_settings
from src.domain.aisle_identification.modes import CONFIGURATION_SNAPSHOT_VERSION
from src.domain.aisle_identification.resolver import resolve_aisle_identification_mode
from src.domain.jobs.entities import Job, JobStatus
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError
from src.domain.ordered_capture.entities import OrderedCaptureSessionStatus
from src.llm.prompt_composer.hybrid_assembly import DEFAULT_HYBRID_PROMPT_PROFILE

logger = logging.getLogger(__name__)

_START_BLOCKING_JOB_STATUSES = (
    JobStatus.QUEUED,
    JobStatus.STARTING,
    JobStatus.RUNNING,
    JobStatus.CANCEL_REQUESTED,
)


def _processing_mode_from_job(job: Job) -> str:
    from src.domain.aisle_identification.processing_mode import (
        DEFAULT_AISLE_PROCESSING_MODE,
        processing_mode_from_identification_execution,
    )

    params = job.engine_params_json if isinstance(job.engine_params_json, dict) else {}
    ident = params.get("identification_execution")
    mode = processing_mode_from_identification_execution(
        ident if isinstance(ident, dict) else None
    )
    return mode.value if mode else DEFAULT_AISLE_PROCESSING_MODE.value


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
    #: AUTO | CODE_SCAN_ONLY | VISION_ONLY — omit for default AUTO (backward compatible).
    requested_processing_mode: str | None = None
    #: Used only when ``resolve_execution_keys`` is false (e.g. unit tests with pre-resolved keys).
    pipeline_provider_key: str = "gemini"
    model_name: str | None = None
    prompt_key: str = DEFAULT_HYBRID_PROMPT_PROFILE
    #: Stable client key; replay returns the existing job for this aisle when found.
    idempotency_key: str | None = None
    #: Authenticated principal (required for user-facing process starts).
    principal: AccessPrincipal | None = None
    #: When set, process requires a SEALED ordered capture session (Phase 1).
    ordered_capture_session_id: str | None = None


@dataclass(frozen=True)
class StartAisleProcessingResult:
    job_id: str
    identification_mode: str
    identification_mode_source: str
    execution_strategy: str
    configuration_snapshot_version: int
    processing_mode: str = "AUTO"


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
        access_policy: InventoryAccessPolicy,
        client_repo: ClientRepository | None = None,
        extraction_profile_repo=None,
        client_supplier_repo: ClientSupplierRepository | None = None,
        supplier_prompt_config_repo: SupplierPromptConfigRepository | None = None,
        label_profile_repo: ClientSupplierLabelProfileRepository | None = None,
        ordered_session_repo: OrderedCaptureSessionRepository | None = None,
        ordered_processing_reservation: OrderedCaptureProcessingReservationService | None = None,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._aisle_repo = aisle_repo
        self._asset_repo = asset_repo
        self._job_repo = job_repo
        self._launch_service = launch_service
        self._stale_reconciler = stale_reconciler
        self._access_policy = access_policy
        self._client_repo = client_repo
        self._extraction_profile_repo = extraction_profile_repo
        self._client_supplier_repo = client_supplier_repo
        self._supplier_prompt_config_repo = supplier_prompt_config_repo
        self._label_profile_repo = label_profile_repo
        self._ordered_session_repo = ordered_session_repo
        self._ordered_processing_reservation = ordered_processing_reservation

    def _mark_ordered_session_processing(
        self,
        sealed_session,
        job: Job,
    ) -> None:
        """SEALED → PROCESSING after job persist; leave alone if already PROCESSING."""
        if self._ordered_session_repo is None:
            return
        current = self._ordered_session_repo.get_by_id(sealed_session.id) or sealed_session
        if current.status != OrderedCaptureSessionStatus.SEALED:
            return
        now = job.started_at or job.created_at
        current.status = OrderedCaptureSessionStatus.PROCESSING
        current.processing_started_at = now
        current.processing_job_id = job.id
        current.updated_at = now
        self._ordered_session_repo.save(current)
        logger.info(
            "processing_started_for_sealed_session capture_session_id=%s job_id=%s "
            "sequence_version=%s",
            current.id,
            job.id,
            current.sequence_version,
        )

    def _embed_exact_label_profile_configurations(
        self,
        *,
        label_profiles_snapshot: dict,
        resolved_profiles,
        client_id: str | None,
    ) -> dict:
        """Load SUPPLIER extraction configs by exact snapshot id/version; fail closed."""
        from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

        out = dict(label_profiles_snapshot)
        for kind, resolved in (
            (LabelKind.ITEM, resolved_profiles.item),
            (LabelKind.POSITION, resolved_profiles.position),
        ):
            if resolved.source is not LabelProfileSource.SUPPLIER:
                continue
            if not (client_id or "").strip():
                raise ValueError(
                    "LABEL_PROFILE_SNAPSHOT_SCOPE_MISMATCH: "
                    "client_id required to embed SUPPLIER extraction configuration"
                )
            key = "item" if kind is LabelKind.ITEM else "position"
            block = out.get(key)
            if not isinstance(block, dict):
                continue
            profile_id = (resolved.extraction_profile_id or "").strip()
            if not profile_id:
                raise ValueError(
                    "SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED: "
                    f"SUPPLIER {kind.value} requires extraction_profile_id in snapshot"
                )
            if self._extraction_profile_repo is None:
                raise ValueError(
                    "SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED: "
                    "extraction profile repository unavailable for exact snapshot load"
                )
            entity = self._extraction_profile_repo.get_by_id(profile_id)
            if entity is None:
                raise ValueError(
                    "SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED: "
                    f"extraction profile {profile_id} not found for {kind.value}"
                )
            if str(entity.client_id).strip() != str(client_id).strip():
                raise ValueError(
                    "LABEL_PROFILE_SNAPSHOT_SCOPE_MISMATCH: "
                    f"extraction profile {profile_id} client_id mismatch"
                )
            expected_supplier = (resolved.client_supplier_id or "").strip()
            if expected_supplier and str(entity.supplier_id).strip() != expected_supplier:
                raise ValueError(
                    "LABEL_PROFILE_SNAPSHOT_SCOPE_MISMATCH: "
                    f"extraction profile {profile_id} supplier_id mismatch"
                )
            entity_kind = entity.label_kind or LabelKind.ITEM
            if entity_kind is not kind:
                raise ValueError(
                    "LABEL_PROFILE_SNAPSHOT_SCOPE_MISMATCH: "
                    f"extraction profile {profile_id} label_kind={entity_kind.value} "
                    f"expected {kind.value}"
                )
            if (
                resolved.extraction_profile_version is not None
                and int(entity.version) != int(resolved.extraction_profile_version)
            ):
                raise ValueError(
                    "LABEL_PROFILE_SNAPSHOT_SCOPE_MISMATCH: "
                    f"extraction profile {profile_id} version={entity.version} "
                    f"expected {resolved.extraction_profile_version}"
                )
            out[key] = {
                **block,
                "extraction_profile_id": entity.id,
                "extraction_profile_version": int(entity.version),
                "configuration": entity.configuration.to_public_dict(),
            }
        return out

    def _return_existing_ordered_job(
        self,
        *,
        sealed_session,
        aisle,
        existing_job: Job,
    ) -> StartAisleProcessingResult:
        job = self._launch_service.ensure_worker_launched_if_needed(
            existing_job,
            aisle,
            log_prefix="job.start_requested",
        )
        self._mark_ordered_session_processing(sealed_session, job)
        logger.info(
            "processing_started_for_sealed_session idempotent "
            "capture_session_id=%s job_id=%s session_status=%s",
            sealed_session.id,
            job.id,
            sealed_session.status.value,
        )
        return StartAisleProcessingResult(
            job_id=job.id,
            identification_mode=job.identification_mode.value,
            identification_mode_source=job.identification_mode_source.value,
            execution_strategy=job.execution_strategy.value,
            configuration_snapshot_version=job.configuration_snapshot_version,
            processing_mode=_processing_mode_from_job(job),
        )

    def execute(self, command: StartAisleProcessingCommand) -> StartAisleProcessingResult:
        if command.principal is None:
            from src.application.dto.access_principal import AccessPrincipalRequiredError

            raise AccessPrincipalRequiredError(
                "StartAisleProcessing requires an AccessPrincipal for user-facing starts"
            )
        self._access_policy.require_aisle(
            command.inventory_id, command.aisle_id, command.principal
        )
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

        aisle_assets = list(self._asset_repo.list_by_aisle(command.aisle_id))
        if not aisle_assets:
            logger.info(
                "aisle.process_rejected_no_source_assets inventory_id=%s aisle_id=%s",
                command.inventory_id,
                command.aisle_id,
            )
            raise NoSourceAssetsForAisleProcessingError(
                f"No source assets for aisle {command.aisle_id}; upload media before processing."
            )

        settings = load_settings()
        ordered_session_id = (command.ordered_capture_session_id or "").strip() or None
        sealed_session = None
        if not ordered_session_id:
            # Auto-detect: if aisle has CLIENT_ASSIGNED sequenced assets, require an explicit sealed session.
            sequenced = [
                a
                for a in aisle_assets
                if a.sequence_source == "CLIENT_ASSIGNED" and a.ordered_capture_session_id
            ]
            if sequenced:
                session_ids = {a.ordered_capture_session_id for a in sequenced}
                if len(session_ids) == 1:
                    ordered_session_id = next(iter(session_ids))
                else:
                    raise ProcessingRejectedUnsealedSessionError(
                        "Aisle has assets from multiple ordered capture sessions; "
                        "pass ordered_capture_session_id explicitly"
                    )

        if ordered_session_id:
            if self._ordered_session_repo is None:
                raise ProcessingRejectedUnsealedSessionError(
                    "Ordered capture session processing is not configured"
                )
            sealed_session = self._ordered_session_repo.get_by_id(ordered_session_id)
            if sealed_session is None:
                raise ProcessingRejectedUnsealedSessionError(
                    f"Ordered capture session not found: {ordered_session_id}"
                )
            if (
                sealed_session.aisle_id != command.aisle_id
                or sealed_session.inventory_id != command.inventory_id
            ):
                raise ProcessingRejectedUnsealedSessionError(
                    "Ordered capture session does not match inventory/aisle"
                )
            session_status = sealed_session.status
            if session_status in (
                OrderedCaptureSessionStatus.OPEN,
                OrderedCaptureSessionStatus.UPLOADING,
            ):
                logger.info(
                    "processing_rejected_unsealed_session capture_session_id=%s status=%s",
                    sealed_session.id,
                    session_status.value,
                )
                raise ProcessingRejectedUnsealedSessionError(
                    "Capture session must be SEALED before processing "
                    f"(status={session_status.value})"
                )

            existing_ordered = self._job_repo.get_by_ordered_capture_session(
                sealed_session.id,
                sequence_version=int(sealed_session.sequence_version),
            )

            if session_status == OrderedCaptureSessionStatus.FAILED:
                if existing_ordered is not None:
                    return self._return_existing_ordered_job(
                        sealed_session=sealed_session,
                        aisle=aisle,
                        existing_job=existing_ordered,
                    )
                raise ProcessingRejectedUnsealedSessionError(
                    "Capture session is FAILED; reseal a new session before processing "
                    f"(status={session_status.value})"
                )

            if session_status in (
                OrderedCaptureSessionStatus.PROCESSING,
                OrderedCaptureSessionStatus.COMPLETED,
            ):
                if existing_ordered is not None:
                    return self._return_existing_ordered_job(
                        sealed_session=sealed_session,
                        aisle=aisle,
                        existing_job=existing_ordered,
                    )
                raise ProcessingRejectedUnsealedSessionError(
                    "Capture session has no job for this sequence version "
                    f"(status={session_status.value})"
                )

            if session_status != OrderedCaptureSessionStatus.SEALED:
                logger.info(
                    "processing_rejected_unsealed_session capture_session_id=%s status=%s",
                    sealed_session.id,
                    session_status.value,
                )
                raise ProcessingRejectedUnsealedSessionError(
                    "Capture session must be SEALED before processing "
                    f"(status={session_status.value})"
                )
            session_assets = [
                a
                for a in aisle_assets
                if (a.ordered_capture_session_id or "") == sealed_session.id
            ]
            expected = int(sealed_session.expected_asset_count or 0)
            reasons = validate_complete_sequence(session_assets, expected_count=expected)
            if reasons:
                raise ProcessingRejectedUnsealedSessionError(
                    "Sealed session sequence incomplete: " + "; ".join(reasons)
                )
            # Prefer session assets only for this job's traversal order.
            aisle_assets = sort_assets_by_logical_sequence(session_assets)
            if existing_ordered is not None:
                return self._return_existing_ordered_job(
                    sealed_session=sealed_session,
                    aisle=aisle,
                    existing_job=existing_ordered,
                )
        elif bool(getattr(settings, "legacy_image_order_enabled", True)):
            logger.info(
                "aisle.process_legacy_image_order inventory_id=%s aisle_id=%s "
                "sequence_source=LEGACY note=uploaded_at_order_not_authoritative",
                command.inventory_id,
                command.aisle_id,
            )
            aisle_assets = sort_assets_by_logical_sequence(aisle_assets)
        else:
            raise ProcessingRejectedUnsealedSessionError(
                "Legacy image order disabled; provide a sealed ordered capture session"
            )

        if bool(
            getattr(settings, "server_skip_remote_code_scan_for_local_authority", False)
        ):
            from src.application.services.authoritative_session_readiness import (
                AuthoritativeSessionReadiness,
            )
            from src.runtime.app_container import get_app_container

            AuthoritativeSessionReadiness(
                asset_repo=self._asset_repo,
                authoritative_repo=get_app_container().get_authoritative_local_code_scan_repo(),
                enabled=True,
            ).require_ready(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
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
                processing_mode=_processing_mode_from_job(existing_idempotent),
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
        from src.domain.aisle_identification.processing_mode import (
            AisleProcessingMode,
            parse_aisle_processing_mode,
        )

        processing_mode = parse_aisle_processing_mode(command.requested_processing_mode)
        resolution = resolve_aisle_identification_mode(
            request_mode=command.requested_identification_mode,
            aisle_mode=aisle.identification_mode,
            inventory_mode=inventory.identification_mode,
            client_mode=client_mode,
        )
        # Central enforcement: block effective LEGACY after full inheritance resolution.
        reject_legacy_effective_mode_for_new_job(
            resolution,
            requested_mode=command.requested_identification_mode,
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
        # VISION_ONLY still runs on the CODE_SCAN worker path with an explicit
        # skip-scanner branch; identification strategy remains CODE_SCAN.
        if (
            processing_mode is AisleProcessingMode.VISION_ONLY
            and execution_strategy.value != "CODE_SCAN"
        ):
            raise ValueError(
                "VISION_ONLY requires CODE_SCAN execution strategy; "
                f"got {execution_strategy.value}"
            )

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
            from src.application.services.image_processing.external_fallback_mode import (
                EXTERNAL_FALLBACK_MODE_PER_ASSET,
                PER_ASSET_DEPRECATION_NOTE,
                parse_external_fallback_mode,
            )

            fallback_mode = parse_external_fallback_mode(
                getattr(settings, "external_fallback_mode", None)
            )
            if fallback_enabled and fallback_mode == EXTERNAL_FALLBACK_MODE_PER_ASSET:
                logger.warning(
                    "aisle.external_fallback_per_asset_deprecated inventory_id=%s "
                    "aisle_id=%s note=%s",
                    command.inventory_id,
                    command.aisle_id,
                    PER_ASSET_DEPRECATION_NOTE,
                )
            settings_provider = str(
                getattr(settings, "external_fallback_provider", "") or ""
            ).strip().lower()
            settings_model = (
                str(getattr(settings, "external_fallback_model", "") or "").strip() or None
            )
            # Prefer process-request provider/model when present (UI Vision selection).
            req_provider = str(pipeline_key or "").strip().lower()
            req_model = str(model_name or "").strip() or None
            provider_key = req_provider or settings_provider
            fallback_model = req_model or settings_model

            # Explicit processing_mode dispatch (do not infer from flags alone).
            if processing_mode is AisleProcessingMode.CODE_SCAN_ONLY:
                fallback_enabled = False
            elif processing_mode is AisleProcessingMode.VISION_ONLY:
                fallback_enabled = True
                if not provider_key or not fallback_model:
                    raise ValueError(
                        "VISION_PROVIDER_NOT_CONFIGURED: "
                        "No hay un proveedor de Vision AI configurado."
                    )
            else:
                # AUTO: productive CODE_SCAN → Vision when provider+model are configured.
                # Kill switch: CODE_SCAN_VISION_FALLBACK_ENABLED=false.
                code_scan_vision = bool(
                    getattr(settings, "code_scan_vision_fallback_enabled", True)
                )
                if (
                    execution_strategy.value == "CODE_SCAN"
                    and code_scan_vision
                    and provider_key
                    and fallback_model
                ):
                    fallback_enabled = True
            if fallback_enabled:
                if not provider_key:
                    raise ValueError(
                        "EXTERNAL_FALLBACK_PROVIDER is required when "
                        "EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=true"
                    )
                if not fallback_model:
                    raise ValueError(
                        "EXTERNAL_FALLBACK_MODEL is required when "
                        "EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=true"
                    )
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
                model=fallback_model,
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
                # Technical failures never go to AI by default (empty allowlist).
                recoverable_technical_codes=sorted(DEFAULT_RECOVERABLE_TECHNICAL_CODES),
                ambiguous_internal_code_fallback_enabled=bool(
                    getattr(
                        settings,
                        "external_fallback_ambiguous_internal_code_enabled",
                        False,
                    )
                ),
                fallback_mode=fallback_mode,
            )
        supplier_prompt_snapshot = None
        if (
            external_fallback is not None
            and bool(external_fallback.get("fallback_enabled"))
            and supplier_id
        ):
            from src.application.services.image_processing.external_fallback_prompt import (
                SupplierPromptConfigError,
                build_resolved_supplier_prompt,
            )
            from src.application.services.supplier_prompt_resolver import (
                SupplierPromptResolutionErrorCode,
                SupplierPromptResolver,
            )

            if self._supplier_prompt_config_repo is None or self._client_supplier_repo is None:
                raise ValueError(
                    "SUPPLIER_PROMPT_REQUIRED: supplier prompt repositories are not configured"
                )
            prompt_resolver = SupplierPromptResolver(
                inventory_repo=self._inventory_repo,
                aisle_repo=self._aisle_repo,
                client_supplier_repo=self._client_supplier_repo,
                supplier_prompt_config_repo=self._supplier_prompt_config_repo,
            )
            supplier_prompt_resolution = prompt_resolver.resolve(
                inventory_id=command.inventory_id,
                aisle_id=command.aisle_id,
                provider_name=str(external_fallback.get("fallback_provider") or "") or None,
                model_name=str(external_fallback.get("fallback_model") or "") or None,
                allow_missing_supplier_prompt_fallback=False,
            )
            if supplier_prompt_resolution.resolution_status != "resolved" or not (
                supplier_prompt_resolution.editable_instructions or ""
            ).strip():
                code = supplier_prompt_resolution.error_code or "SUPPLIER_PROMPT_REQUIRED"
                if code == SupplierPromptResolutionErrorCode.NO_ACTIVE_SUPPLIER_PROMPT_CONFIG:
                    code = "SUPPLIER_PROMPT_REQUIRED"
                elif code == SupplierPromptResolutionErrorCode.CLIENT_SUPPLIER_NOT_FOUND:
                    code = "SUPPLIER_NOT_RESOLVED"
                raise ValueError(
                    f"{code}: active non-empty supplier prompt is required when "
                    "external fallback is enabled for a supplier-associated aisle"
                )
            try:
                profile_id = None
                if isinstance(supplier_extraction_profile, dict):
                    profile_id = supplier_extraction_profile.get("supplier_profile_id")
                resolved_prompt = build_resolved_supplier_prompt(
                    supplier_id=str(
                        supplier_prompt_resolution.client_supplier_id or supplier_id
                    ),
                    prompt_id=str(supplier_prompt_resolution.supplier_prompt_config_id),
                    prompt_version=int(
                        supplier_prompt_resolution.supplier_prompt_config_version or 1
                    ),
                    content=str(supplier_prompt_resolution.editable_instructions),
                    extraction_profile_id=str(profile_id) if profile_id else None,
                    source_level="aisle.client_supplier.supplier_prompt_configs",
                    is_active=True,
                )
            except SupplierPromptConfigError as exc:
                raise ValueError(f"{exc.code}: {exc.message}") from exc
            supplier_prompt_snapshot = resolved_prompt.public_snapshot(include_content=True)
        label_profiles_snapshot = None
        if self._label_profile_repo is not None and self._client_supplier_repo is not None:
            profile_resolver = LabelProfileResolver(
                label_profile_repo=self._label_profile_repo,
                client_supplier_repo=self._client_supplier_repo,
                extraction_profile_repo=self._extraction_profile_repo,
                supplier_prompt_config_repo=self._supplier_prompt_config_repo,
            )
            try:
                resolved_profiles = profile_resolver.resolve(
                    LabelProfileResolutionContext(
                        client_id=client_id,
                        client_supplier_id=str(supplier_id).strip() if supplier_id else None,
                        aisle=aisle,
                    )
                )
            except SupplierLabelProfileNotConfiguredError:
                raise
            label_profiles_snapshot = resolved_profiles.to_snapshot_dict()
            # Exact profile id/version → embed immutable configuration (not legacy blob).
            label_profiles_snapshot = self._embed_exact_label_profile_configurations(
                label_profiles_snapshot=label_profiles_snapshot,
                resolved_profiles=resolved_profiles,
                client_id=client_id,
            )
        engine_params_json = {
            "identification_execution": identification_execution_snapshot_dict(
                decision,
                ocr_config=ocr_config,
                client_rules=ocr_client_rules_snapshot(client_rules),
                configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
                external_fallback=external_fallback,
                supplier_extraction_profile=supplier_extraction_profile,
                supplier_prompt=supplier_prompt_snapshot,
                label_profiles=label_profiles_snapshot,
                client_extraction_profiles_enabled=profiles_enabled,
                profile_aware_validation_enabled=profile_aware,
                reference_template_annotations_enabled=annotations_enabled,
                profile_snapshotted=bool(supplier_extraction_profile),
                profile_validation_executed=False,
                processing_mode=processing_mode.value,
            ),
            "client_id": client_id,
            "supplier_id": str(supplier_id).strip() if supplier_id else None,
        }

        logger.info(
            "aisle.identification_resolved inventory_id=%s aisle_id=%s "
            "requested_identification_mode=%s configured_aisle=%s configured_inventory=%s "
            "configured_client=%s effective_identification_mode=%s identification_mode_source=%s "
            "configuration_snapshot_version=%s aisle_identification_pipeline_enabled=%s "
            "actual_execution_strategy=%s execution_reason=%s processing_mode=%s "
            "vision_fallback_enabled=%s",
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
            processing_mode.value,
            bool(
                isinstance(external_fallback, dict)
                and external_fallback.get("fallback_enabled")
            ),
        )

        payload: ProcessAislePayload = {"aisle_id": command.aisle_id}
        if command.idempotency_key and str(command.idempotency_key).strip():
            payload["idempotency_key"] = str(command.idempotency_key).strip()
        if sealed_session is not None:
            payload["ordered_capture_session_id"] = sealed_session.id
            payload["sequence_version"] = int(sealed_session.sequence_version)
        try:
            from src.application.use_cases.recovery.recover_stale_job import (
                ensure_payload_correlation,
            )
            from src.observability.context import get_correlation_id
            from src.observability.request_ids import generate_correlation_id

            corr = get_correlation_id() or generate_correlation_id()
            payload = ensure_payload_correlation(dict(payload), corr)  # type: ignore[assignment]
        except Exception:
            logger.warning("correlation inject failed aisle_id=%s", command.aisle_id, exc_info=True)

        if sealed_session is not None:
            # Ordered path: reserve SEALED→PROCESSING + unique job in one transaction,
            # then launch worker only after commit.
            if self._ordered_processing_reservation is None:
                raise ProcessingRejectedUnsealedSessionError(
                    "Ordered capture session processing reservation is not configured"
                )
            job_template = self._launch_service.build_attempt_job(
                aisle=aisle,
                payload=payload,
                attempt_count=1,
                retry_of_job_id=None,
                provider_name=pipeline_key,
                model_name=model_name,
                prompt_key=prompt_key,
                identification_mode=resolution.effective_mode,
                identification_mode_source=resolution.source,
                configuration_snapshot_version=CONFIGURATION_SNAPSHOT_VERSION,
                execution_strategy=execution_strategy,
                engine_params_json=engine_params_json,
            )
            reservation = self._ordered_processing_reservation.reserve(
                job_template,
                sealed_session,
                now=job_template.started_at or job_template.created_at,
            )
            job = reservation.job
            if reservation.created:
                job = self._launch_service.launch_persisted_attempt(
                    job,
                    aisle,
                    log_prefix="job.start_requested",
                    retry_of_job_id=None,
                )
            else:
                job = self._launch_service.ensure_worker_launched_if_needed(
                    job,
                    aisle,
                    log_prefix="job.start_requested",
                    retry_of_job_id=None,
                )
            return StartAisleProcessingResult(
                job_id=job.id,
                identification_mode=job.identification_mode.value,
                identification_mode_source=job.identification_mode_source.value,
                execution_strategy=job.execution_strategy.value,
                configuration_snapshot_version=job.configuration_snapshot_version,
                processing_mode=processing_mode.value,
            )

        # Legacy (non-ordered) path: create and launch unchanged.
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
            processing_mode=processing_mode.value,
        )
