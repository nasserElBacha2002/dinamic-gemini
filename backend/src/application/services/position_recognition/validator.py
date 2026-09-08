"""Authoritative canonical position validator used by backend entry points."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from src.application.services.label_validation import LabelValidationService
from src.application.services.position_recognition.normalization import (
    PositionCodeNormalizationError,
    normalize_position_code,
)
from src.application.services.positioning_label_signing import PositioningLabelSigningService
from src.domain.aisle_location.label_entities import POSITIONING_LABEL_TYPE
from src.domain.aisle_location.payload import validate_positioning_payload
from src.domain.label_profiles.kinds import LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationStatus,
    NormalizedPositionLabel,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.position_recognition import (
    CanonicalPositionRecognition,
    CanonicalPositionValidationResult,
    CanonicalPositionValidationStatus,
    PositionRecognitionSource,
    PositionSignatureEvidence,
    PositionSignatureVerification,
)


class PositionLabelResolverPort(Protocol):
    def resolve(
        self, *, public_label_id: str, expected_client_id: str
    ): ...  # PositionLabelResolveResult without coupling this contract to persistence.


@dataclass(frozen=True)
class PositionCompatibilityPolicy:
    """Server-controlled compatibility policy; clients cannot override it."""

    signature_required: bool = True
    preexistence_required: bool = True
    flexible_validation_enabled: bool = False

    @classmethod
    def resolve(
        cls,
        *,
        signature_required: bool,
        preexistence_required: bool,
        flexible_validation_enabled: bool,
    ) -> PositionCompatibilityPolicy:
        # Disabling a legacy gate has no effect until flexible validation is
        # deliberately enabled, avoiding contradictory partial deployments.
        flexible = bool(flexible_validation_enabled)
        return cls(
            signature_required=bool(signature_required) or not flexible,
            preexistence_required=bool(preexistence_required) or not flexible,
            flexible_validation_enabled=flexible,
        )


@dataclass(frozen=True)
class CanonicalPositionValidationCommand:
    candidate: CandidateLabel
    source: PositionRecognitionSource
    context: LabelValidationContext
    company_id: str | None = None
    inventory_id: str | None = None
    aisle_id: str | None = None
    client_supplier_id: str | None = None
    inventory_writable: bool = True


class CanonicalPositionValidator:
    """Recognize/validate first; resolve existing Dinamic labels second."""

    def __init__(
        self,
        *,
        label_validator: LabelValidationService | None = None,
        signing: PositioningLabelSigningService | None = None,
        resolver: PositionLabelResolverPort | None = None,
        policy: PositionCompatibilityPolicy | None = None,
    ) -> None:
        self._labels = label_validator or LabelValidationService()
        self._signing = signing
        self._resolver = resolver
        self._policy = policy or PositionCompatibilityPolicy()

    def validate(
        self, command: CanonicalPositionValidationCommand
    ) -> CanonicalPositionValidationResult:
        self._metric("position_recognition_total", command)
        if not command.inventory_writable:
            return self._finish(
                command,
                CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.INVENTORY_NOT_WRITABLE,
                    error_code="INVENTORY_NOT_WRITABLE",
                ),
            )

        raw = command.candidate.raw_payload
        dinamic_payload = self._parse_dinamic_payload(raw)
        if dinamic_payload is not None:
            result = self._validate_dinamic(command, dinamic_payload)
        else:
            result = self._validate_profile_position(command)
        return self._finish(command, result)

    @staticmethod
    def _parse_dinamic_payload(raw: str) -> dict | None:
        try:
            parsed = json.loads((raw or "").strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if isinstance(parsed, dict) and parsed.get("type") == POSITIONING_LABEL_TYPE:
            return parsed
        return None

    def _validate_dinamic(
        self,
        command: CanonicalPositionValidationCommand,
        payload: dict,
    ) -> CanonicalPositionValidationResult:
        try:
            validate_positioning_payload(payload)
            code = normalize_position_code(str(payload["label_id"]))
        except (ValueError, PositionCodeNormalizationError) as exc:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INVALID_FORMAT,
                error_code=getattr(exc, "code", "DINAMIC_POSITION_INVALID"),
                detail=str(exc),
            )

        signature_present = bool(str(payload.get("signature") or "").strip())
        key_version = (
            int(payload["key_version"]) if payload.get("key_version") is not None else None
        )
        verification = (
            PositionSignatureVerification.UNVERIFIED
            if signature_present
            else PositionSignatureVerification.MISSING
        )
        if signature_present:
            if self._signing is None:
                verification = PositionSignatureVerification.UNVERIFIED
            else:
                try:
                    verification = (
                        PositionSignatureVerification.VERIFIED
                        if self._signing.verify_payload(payload)
                        else PositionSignatureVerification.INVALID
                    )
                except ValueError:
                    verification = PositionSignatureVerification.INVALID

        recognition = CanonicalPositionRecognition(
            raw_code=raw_or_empty(command.candidate.raw_payload),
            normalized_code=code.normalized_code,
            source=command.source,
            pallet=_optional_text(payload.get("pallet")),
            side=_optional_upper(payload.get("side")),
            level=_optional_int(payload.get("level")),
            marker_index=_optional_int(payload.get("marker_index")),
            marker_total=_optional_int(payload.get("marker_total")),
            signature=PositionSignatureEvidence(
                present=signature_present,
                verification=verification,
                key_version=key_version,
            ),
            evidence={
                "format": POSITIONING_LABEL_TYPE,
                "payload_version": int(payload["version"]),
            },
        )

        if verification is PositionSignatureVerification.INVALID:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INVALID_SIGNATURE,
                recognition=recognition,
                error_code="INVALID_SIGNATURE",
            )
        if verification is PositionSignatureVerification.UNVERIFIED:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                recognition=recognition,
                error_code="SIGNATURE_VERIFIER_UNAVAILABLE",
            )
        if (
            verification is PositionSignatureVerification.MISSING
            and self._policy.signature_required
        ):
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.SIGNATURE_REQUIRED_BY_LEGACY_POLICY,
                recognition=recognition,
                error_code="SIGNATURE_REQUIRED_BY_LEGACY_POLICY",
                policy_rejection=True,
            )

        return self._resolve_dinamic(
            command,
            recognition,
            exact_public_identifier=code.raw_code,
        )

    def _resolve_dinamic(
        self,
        command: CanonicalPositionValidationCommand,
        recognition: CanonicalPositionRecognition,
        *,
        exact_public_identifier: str,
    ) -> CanonicalPositionValidationResult:
        client_id = (command.context.client_id or "").strip()
        if self._resolver is None or not client_id:
            if self._policy.preexistence_required:
                return CanonicalPositionValidationResult(
                    status=(
                        CanonicalPositionValidationStatus.PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY
                    ),
                    recognition=recognition,
                    error_code="PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY",
                    policy_rejection=True,
                )
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
                recognition=recognition,
            )

        try:
            resolved = self._resolver.resolve(
                public_label_id=exact_public_identifier,
                expected_client_id=client_id,
            )
        except Exception:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                recognition=recognition,
                error_code="POSITION_RESOLUTION_FAILED",
            )

        if resolved.detection_status is PositionLabelDetectionStatus.VALID:
            label = resolved.label
            if label is None:
                return CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                    recognition=recognition,
                    error_code="POSITION_RESOLUTION_INCOMPLETE",
                )
            if not _recognition_matches_catalog(
                recognition,
                getattr(label, "canonical_payload", None),
            ):
                return CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION,
                    recognition=recognition,
                    error_code="POSITION_CATALOG_HIERARCHY_MISMATCH",
                )
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.VALID_EXISTING,
                recognition=recognition,
                existing_position_label_id=label.id,
            )
        if resolved.detection_status is PositionLabelDetectionStatus.LABEL_NOT_FOUND:
            status = (
                CanonicalPositionValidationStatus.PREEXISTENCE_REQUIRED_BY_LEGACY_POLICY
                if self._policy.preexistence_required
                else CanonicalPositionValidationStatus.VALID_UNMATERIALIZED
            )
            return CanonicalPositionValidationResult(
                status=status,
                recognition=recognition,
                error_code=status.value if self._policy.preexistence_required else None,
                policy_rejection=self._policy.preexistence_required,
            )
        if resolved.detection_status is PositionLabelDetectionStatus.CLIENT_MISMATCH:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED,
                recognition=recognition,
                error_code="POSITION_SCOPE_MISMATCH",
            )
        return CanonicalPositionValidationResult(
            status=CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION,
            recognition=recognition,
            error_code="POSITION_NOT_ACTIVE",
        )

    def _validate_profile_position(
        self,
        command: CanonicalPositionValidationCommand,
    ) -> CanonicalPositionValidationResult:
        profile = (
            command.context.resolved_profiles.position
            if command.context.resolved_profiles is not None
            else None
        )
        if (
            command.client_supplier_id
            and profile is not None
            and profile.client_supplier_id
            and command.client_supplier_id.strip() != profile.client_supplier_id.strip()
        ):
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED,
                error_code="POSITION_SUPPLIER_SCOPE_MISMATCH",
            )
        result = self._labels.validate_best_effort(command.candidate, context=command.context)
        if result.status is LabelValidationStatus.AMBIGUOUS:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.AMBIGUOUS_CODE,
                error_code="AMBIGUOUS_CODE",
            )
        if result.status is not LabelValidationStatus.VALID:
            return CanonicalPositionValidationResult(
                status=self._map_label_error(result.error_code),
                error_code=result.error_code or "INVALID_FORMAT",
                detail=result.detail,
            )
        if not isinstance(result.label, NormalizedPositionLabel):
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INVALID_FORMAT,
                error_code="LABEL_KIND_IS_NOT_POSITION",
            )
        try:
            code = normalize_position_code(result.label.position_id)
        except PositionCodeNormalizationError as exc:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION,
                error_code=exc.code,
                detail=str(exc),
            )
        return CanonicalPositionValidationResult(
            status=CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
            recognition=CanonicalPositionRecognition(
                raw_code=raw_or_empty(command.candidate.raw_payload),
                normalized_code=code.normalized_code,
                source=command.source,
                pallet=_optional_text(result.label.pallet),
                side=_optional_upper(result.label.side),
                level=_optional_int(result.label.level),
                profile_id=profile.extraction_profile_id if profile else None,
                profile_version=profile.extraction_profile_version if profile else None,
                client_supplier_id=(
                    command.client_supplier_id or (profile.client_supplier_id if profile else None)
                ),
                signature=PositionSignatureEvidence(
                    present=False,
                    verification=PositionSignatureVerification.NOT_APPLICABLE,
                ),
                evidence={
                    "profile_source": (
                        result.label.profile_source.value
                        if isinstance(result.label.profile_source, LabelProfileSource)
                        else str(result.label.profile_source)
                    )
                },
            ),
        )

    @staticmethod
    def _map_label_error(error_code: str | None) -> CanonicalPositionValidationStatus:
        if error_code == LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value:
            return CanonicalPositionValidationStatus.AMBIGUOUS_CODE
        if error_code == LabelValidationErrorCode.LABEL_CHECKSUM_FAILED.value:
            return CanonicalPositionValidationStatus.INVALID_CHECKSUM
        if error_code == LabelValidationErrorCode.LABEL_GS1_CHECK_DIGIT_FAILED.value:
            return CanonicalPositionValidationStatus.INVALID_CHECKSUM
        if error_code in {
            LabelValidationErrorCode.SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED.value,
            LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
        }:
            return CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED
        if error_code in {
            LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
            LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
            LabelValidationErrorCode.LABEL_LENGTH_MISMATCH.value,
            LabelValidationErrorCode.LABEL_CHARSET_MISMATCH.value,
        }:
            return CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION
        return CanonicalPositionValidationStatus.INVALID_FORMAT

    def _finish(
        self,
        command: CanonicalPositionValidationCommand,
        result: CanonicalPositionValidationResult,
    ) -> CanonicalPositionValidationResult:
        self._metric("position_validation_by_source_total", command)
        self._metric("position_validation_by_profile_total", command)
        if result.status is CanonicalPositionValidationStatus.VALID_UNMATERIALIZED:
            self._metric("position_valid_unmaterialized_total", command)
        elif result.status is CanonicalPositionValidationStatus.AMBIGUOUS_CODE:
            self._metric("position_ambiguous_total", command)
        elif result.policy_rejection:
            self._metric("position_legacy_policy_rejected_total", command, result=result)
        elif not result.operationally_accepted:
            self._metric("position_validation_rejected_total", command, result=result)
        return result

    @staticmethod
    def _metric(
        name: str,
        command: CanonicalPositionValidationCommand,
        *,
        result: CanonicalPositionValidationResult | None = None,
    ) -> None:
        from src.observability.metrics.registry import get_metrics_registry

        profile = (
            command.context.resolved_profiles.position
            if command.context.resolved_profiles is not None
            else None
        )
        labels = {
            "component": command.source.value,
            "mode": profile.source.value if profile else "DEFAULT",
        }
        if result is not None:
            labels["reason"] = result.status.value
        get_metrics_registry().inc(name, "Canonical position recognition outcome", labels)


def raw_or_empty(raw: str | None) -> str:
    return raw if isinstance(raw, str) else ""


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_upper(value: object) -> str | None:
    text = _optional_text(value)
    return text.upper() if text else None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _recognition_matches_catalog(
    recognition: CanonicalPositionRecognition,
    canonical_payload: object,
) -> bool:
    if not isinstance(canonical_payload, dict):
        return True
    comparisons = {
        "label_id": recognition.normalized_code,
        "pallet": recognition.pallet,
        "side": recognition.side,
        "level": recognition.level,
        "marker_index": recognition.marker_index,
        "marker_total": recognition.marker_total,
    }
    for key, recognized in comparisons.items():
        if recognized is None or key not in canonical_payload:
            continue
        catalog = canonical_payload[key]
        if key in {"level", "marker_index", "marker_total"}:
            if _optional_int(catalog) != recognized:
                return False
        elif _optional_upper(catalog) != _optional_upper(recognized):
            return False
    return True
