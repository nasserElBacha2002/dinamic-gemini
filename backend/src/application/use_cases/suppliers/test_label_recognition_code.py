"""Non-persistent label-recognition code tester (PR2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.application.errors import (
    SupplierExtractionProfileInvalidConfigurationError,
)
from src.application.ports.repositories import ClientRepository, ClientSupplierRepository
from src.application.ports.supplier_extraction_profile_repository import (
    SupplierExtractionProfileRepository,
)
from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.label_validation import (
    LabelProfileConfigurationError,
    LabelValidationService,
    StructuredPayloadExtractor,
    validate_extraction_configuration_for_code_scan,
)
from src.application.use_cases.suppliers.manage_supplier_extraction_profiles import (
    _ensure_profile_in_scope,
    _validate_supplier_in_client_scope,
)
from src.domain.client_supplier.extraction_profile import ExtractionProfileConfiguration
from src.domain.label_profiles.entities import ResolvedLabelProfile, ResolvedLabelProfiles
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    RecognitionSource,
)
from src.domain.label_validation.context import LabelValidationContext

_MAX_TEST_PAYLOAD = 512


@dataclass(frozen=True)
class LabelRecognitionCodeTestCommand:
    client_id: str
    supplier_id: str
    label_kind: LabelKind
    raw_payload: str
    symbology: str | None = None
    profile_id: str | None = None
    configuration: dict[str, Any] | None = None


class LabelRecognitionCodeTesterUseCase:
    """Dry-run StructuredPayloadExtractor + LabelValidationService; never persists."""

    def __init__(
        self,
        *,
        client_repo: ClientRepository,
        client_supplier_repo: ClientSupplierRepository,
        profile_repo: SupplierExtractionProfileRepository,
        validation_service: LabelValidationService | None = None,
    ) -> None:
        self._client_repo = client_repo
        self._client_supplier_repo = client_supplier_repo
        self._profile_repo = profile_repo
        self._validation = validation_service or LabelValidationService()
        self._extractor = StructuredPayloadExtractor()

    def execute(self, command: LabelRecognitionCodeTestCommand) -> dict[str, Any]:
        _validate_supplier_in_client_scope(
            client_repo=self._client_repo,
            client_supplier_repo=self._client_supplier_repo,
            client_id=command.client_id,
            supplier_id=command.supplier_id,
        )
        raw = command.raw_payload if command.raw_payload is not None else ""
        if len(raw) > _MAX_TEST_PAYLOAD:
            raise ValueError("raw_payload exceeds length limit")

        configuration = self._resolve_configuration(command)
        try:
            validate_extraction_configuration_for_code_scan(configuration)
        except LabelProfileConfigurationError as exc:
            raise SupplierExtractionProfileInvalidConfigurationError(exc.message) from exc

        context = LabelValidationContext(
            resolved_profiles=ResolvedLabelProfiles(
                item=ResolvedLabelProfile(
                    label_kind=LabelKind.ITEM,
                    source=LabelProfileSource.SUPPLIER,
                    client_supplier_id=command.supplier_id,
                    resolution_source="TESTER",
                ),
                position=ResolvedLabelProfile(
                    label_kind=LabelKind.POSITION,
                    source=LabelProfileSource.SUPPLIER,
                    client_supplier_id=command.supplier_id,
                    resolution_source="TESTER",
                ),
            ),
            item_extraction_configuration=(
                configuration if command.label_kind is LabelKind.ITEM else None
            ),
            position_extraction_configuration=(
                configuration if command.label_kind is LabelKind.POSITION else None
            ),
        )

        extracted = self._extractor.extract(
            raw_payload=raw,
            configuration=configuration,
            label_kind=command.label_kind,
            symbology=command.symbology,
            recognition_source=RecognitionSource.CODE_SCAN,
        )
        result = self._validation.validate(
            CandidateLabel(
                raw_payload=raw,
                recognition_source=RecognitionSource.CODE_SCAN,
                symbology=command.symbology,
                label_kind_hint=command.label_kind,
            ),
            context=context,
            label_kind=command.label_kind,
        )

        rules = configuration.effective_deterministic()
        extracted_fields: dict[str, Any] = {}
        if extracted.candidate is not None:
            cand = extracted.candidate
            extracted_fields = {
                "label_id": cand.label_id,
                "sku": cand.sku,
                "quantity": cand.quantity,
                "position_id": cand.position_id,
                "pallet": cand.pallet,
                "side": cand.side,
                "level": cand.level,
                "lot": cand.metadata.get("lot"),
                "serial": cand.metadata.get("serial"),
                "expiry_date": cand.metadata.get("expiry_date"),
            }
        ais = None
        if extracted.candidate and extracted.candidate.metadata.get(
            "gs1_application_identifiers"
        ):
            ais = [
                a
                for a in extracted.candidate.metadata[
                    "gs1_application_identifiers"
                ].split(",")
                if a
            ]

        return {
            "label_kind": command.label_kind.value,
            "profile_source": LabelProfileSource.SUPPLIER.value,
            "structure": rules.payload_structure.value,
            "raw_payload": raw,
            "normalized_payload": extracted.normalized_payload,
            "extracted_fields": extracted_fields,
            "validation_status": result.status.value,
            "error_code": result.error_code or extracted.error_code,
            "diagnostics": {
                **(result.diagnostics or {}),
                "extraction_error": extracted.detail,
                "extraction_error_code": extracted.error_code,
            },
            "application_identifiers": ais,
            "persists_inventory": False,
        }

    def _resolve_configuration(
        self, command: LabelRecognitionCodeTestCommand
    ) -> ExtractionProfileConfiguration:
        if command.configuration is not None:
            try:
                return parse_extraction_configuration(command.configuration)
            except ExtractionProfileConfigurationError as exc:
                raise SupplierExtractionProfileInvalidConfigurationError(
                    exc.message
                ) from exc
        if not command.profile_id:
            raise ValueError("profile_id or configuration is required")
        profile = _ensure_profile_in_scope(
            self._profile_repo.get_by_id(command.profile_id),
            client_id=command.client_id,
            supplier_id=command.supplier_id,
            profile_id=command.profile_id,
        )
        return profile.configuration
