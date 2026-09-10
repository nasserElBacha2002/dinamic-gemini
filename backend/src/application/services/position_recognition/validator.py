"""Authoritative canonical position validator used by backend entry points."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from src.application.services.label_validation import LabelValidationService
from src.application.services.position_label_detection.position_label_policy import (
    is_unsigned_legacy_catalog_match,
)
from src.application.services.position_label_detection.resolver import (
    PositionLabelResolutionUnavailableError,
)
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
    LabelValidationResult,
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
    PositionResolutionStatus,
    PositionSignatureEvidence,
    PositionSignaturePolicy,
    PositionSignatureVerification,
)

logger = logging.getLogger(__name__)


class PositionLabelResolverPort(Protocol):
    def resolve(
        self, *, public_label_id: str, expected_client_id: str
    ): ...  # PositionLabelResolveResult without coupling this contract to persistence.


@dataclass(frozen=True)
class PositionCompatibilityPolicy:
    """Server-controlled compatibility policy; clients cannot override it."""

    signature_validation_enabled: bool = True
    allow_unsigned_legacy: bool = False
    preexistence_required: bool = True
    flexible_validation_enabled: bool = False
    signature_policy: PositionSignaturePolicy = PositionSignaturePolicy.REQUIRED

    @classmethod
    def resolve(
        cls,
        *,
        signature_validation_enabled: bool,
        allow_unsigned_legacy: bool = False,
        preexistence_required: bool,
        flexible_validation_enabled: bool,
        signature_policy: PositionSignaturePolicy | str = PositionSignaturePolicy.REQUIRED,
    ) -> PositionCompatibilityPolicy:
        flexible = bool(flexible_validation_enabled)
        if not flexible and not preexistence_required:
            raise PositionPolicyConfigurationError(
                "POSITION_PREEXISTENCE_REQUIRED=false requires "
                "POSITION_FLEXIBLE_VALIDATION_ENABLED=true"
            )
        policy = (
            signature_policy
            if isinstance(signature_policy, PositionSignaturePolicy)
            else PositionSignaturePolicy(str(signature_policy).strip().upper())
        )
        return cls(
            signature_validation_enabled=bool(signature_validation_enabled),
            allow_unsigned_legacy=bool(allow_unsigned_legacy),
            preexistence_required=bool(preexistence_required),
            flexible_validation_enabled=flexible,
            signature_policy=policy,
        )


class PositionPolicyConfigurationError(ValueError):
    """Contradictory server-side position policy configuration."""


@dataclass(frozen=True)
class CanonicalPositionValidationCommand:
    candidate: CandidateLabel
    source: PositionRecognitionSource
    context: LabelValidationContext
    client_supplier_id: str | None = None
    structural_result: LabelValidationResult | None = None


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

    @property
    def policy(self) -> PositionCompatibilityPolicy:
        return self._policy

    def with_policy(self, policy: PositionCompatibilityPolicy) -> CanonicalPositionValidator:
        """Return a validator sharing adapters but using a different policy snapshot."""
        return CanonicalPositionValidator(
            label_validator=self._labels,
            signing=self._signing,
            resolver=self._resolver,
            policy=policy,
        )

    def _effective_signature_policy(
        self, command: CanonicalPositionValidationCommand
    ) -> PositionSignaturePolicy:
        """Profile policy wins when present; settings policy is the default/kill-switch."""
        profiles = command.context.resolved_profiles
        if profiles is not None:
            profile_policy = getattr(profiles.position, "signature_policy", None)
            if profile_policy is not None:
                if isinstance(profile_policy, PositionSignaturePolicy):
                    return profile_policy
                return PositionSignaturePolicy(str(profile_policy).strip().upper())
        return self._policy.signature_policy

    def validate(
        self,
        command: CanonicalPositionValidationCommand,
        *,
        evaluate_preexistence: bool = True,
        record_operational_metrics: bool = True,
    ) -> CanonicalPositionValidationResult:
        if record_operational_metrics:
            self._metric("position_recognition_total", command)
        raw = command.candidate.raw_payload
        dinamic_payload = self._prevalidated_dinamic_payload(command.structural_result)
        structurally_validated = dinamic_payload is not None
        if dinamic_payload is None:
            dinamic_payload = self._parse_dinamic_payload(raw)
        if dinamic_payload is not None:
            result = self._validate_dinamic(
                command,
                dinamic_payload,
                evaluate_preexistence=evaluate_preexistence,
                structurally_validated=structurally_validated,
            )
        else:
            result = self._validate_profile_position(command)
        return self._finish(
            command,
            result,
            record_operational_metrics=record_operational_metrics,
        )

    @staticmethod
    def _parse_dinamic_payload(raw: str) -> dict | None:
        try:
            parsed = json.loads((raw or "").strip())
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if isinstance(parsed, dict) and parsed.get("type") == POSITIONING_LABEL_TYPE:
            return parsed
        return None

    @staticmethod
    def _prevalidated_dinamic_payload(
        result: LabelValidationResult | None,
    ) -> dict | None:
        if (
            result is None
            or result.status is not LabelValidationStatus.VALID
            or not isinstance(result.label, NormalizedPositionLabel)
            or result.label.profile_source is not LabelProfileSource.DINAMIC
        ):
            return None
        payload = result.diagnostics.get("position_payload")
        if isinstance(payload, dict) and payload.get("type") == POSITIONING_LABEL_TYPE:
            return dict(payload)
        return None

    def _validate_dinamic(
        self,
        command: CanonicalPositionValidationCommand,
        payload: dict,
        *,
        evaluate_preexistence: bool,
        structurally_validated: bool,
    ) -> CanonicalPositionValidationResult:
        try:
            if not structurally_validated:
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
        signature_policy = self._effective_signature_policy(command)
        if signature_policy is PositionSignaturePolicy.NOT_APPLICABLE:
            verification = PositionSignatureVerification.NOT_APPLICABLE
        else:
            verification = (
                PositionSignatureVerification.UNVERIFIED
                if signature_present
                else PositionSignatureVerification.MISSING
            )
            if signature_present and self._policy.signature_validation_enabled:
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
                "signature_policy": signature_policy.value,
            },
        )

        if signature_policy is PositionSignaturePolicy.NOT_APPLICABLE:
            if signature_present:
                return CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.SIGNATURE_NOT_ALLOWED_FOR_PROFILE,
                    recognition=recognition,
                    error_code="SIGNATURE_NOT_ALLOWED_FOR_PROFILE",
                    policy_rejection=True,
                )
            return self._resolve_dinamic(
                command,
                recognition,
                exact_public_identifier=code.raw_code,
                evaluate_preexistence=evaluate_preexistence,
                unsigned_legacy_candidate=False,
                payload_version=int(payload["version"]),
            )

        if signature_present and not self._policy.signature_validation_enabled:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.SIGNATURE_VALIDATION_SKIPPED,
                recognition=recognition,
                error_code="SIGNATURE_VALIDATION_SKIPPED",
            )
        # INVALID is never equated with MISSING, regardless of REQUIRED/OPTIONAL.
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

        unsigned_legacy_candidate = False
        if verification is PositionSignatureVerification.MISSING:
            if signature_policy is PositionSignaturePolicy.OPTIONAL:
                # Missing signature is allowed; continue to resolve/materialize.
                unsigned_legacy_candidate = False
            elif self._policy.allow_unsigned_legacy:
                # REQUIRED + unsigned-legacy catalog path (legacy Dinamic).
                unsigned_legacy_candidate = True
            else:
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
            evaluate_preexistence=evaluate_preexistence,
            unsigned_legacy_candidate=unsigned_legacy_candidate,
            payload_version=int(payload["version"]),
        )

    def _resolve_dinamic(
        self,
        command: CanonicalPositionValidationCommand,
        recognition: CanonicalPositionRecognition,
        *,
        exact_public_identifier: str,
        evaluate_preexistence: bool,
        unsigned_legacy_candidate: bool,
        payload_version: int,
    ) -> CanonicalPositionValidationResult:
        client_id = (command.context.client_id or "").strip()
        if not evaluate_preexistence:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.VALID_PENDING_RESOLUTION,
                recognition=recognition,
                resolution_status=PositionResolutionStatus.NOT_EVALUATED,
            )
        if not client_id:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                recognition=recognition,
                error_code="POSITION_CLIENT_CONTEXT_MISSING",
                resolution_status=PositionResolutionStatus.ERROR,
            )
        if self._resolver is None:
            if unsigned_legacy_candidate:
                return self._unsigned_legacy_rejection(recognition)
            if not self._policy.preexistence_required:
                return CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.VALID_UNMATERIALIZED,
                    recognition=recognition,
                    resolution_status=PositionResolutionStatus.NOT_EVALUATED,
                )
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                recognition=recognition,
                error_code="POSITION_RESOLVER_UNAVAILABLE",
                resolution_status=PositionResolutionStatus.ERROR,
            )

        try:
            resolved = self._resolver.resolve(
                public_label_id=exact_public_identifier,
                expected_client_id=client_id,
            )
        except PositionLabelResolutionUnavailableError:
            logger.warning(
                "position_resolution_unavailable job_id=%s client_id=%s source=%s",
                command.context.job_id,
                client_id,
                command.source.value,
            )
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                recognition=recognition,
                error_code="POSITION_RESOLUTION_UNAVAILABLE",
                resolution_status=PositionResolutionStatus.ERROR,
            )

        if resolved.detection_status is PositionLabelDetectionStatus.VALID:
            label = resolved.label
            if label is None:
                return CanonicalPositionValidationResult(
                    status=CanonicalPositionValidationStatus.INTERNAL_ERROR,
                    recognition=recognition,
                    error_code="POSITION_RESOLUTION_INCOMPLETE",
                )
            if unsigned_legacy_candidate and not is_unsigned_legacy_catalog_match(
                parsed_label_id=exact_public_identifier,
                parsed_version=payload_version,
                label=label,
            ):
                return self._unsigned_legacy_rejection(recognition)
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
                resolution_status=PositionResolutionStatus.EXISTING,
            )
        if resolved.detection_status is PositionLabelDetectionStatus.LABEL_NOT_FOUND:
            if unsigned_legacy_candidate:
                return self._unsigned_legacy_rejection(recognition)
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
                resolution_status=PositionResolutionStatus.NOT_FOUND,
            )
        if resolved.detection_status is PositionLabelDetectionStatus.CLIENT_MISMATCH:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.PROFILE_NOT_ALLOWED,
                recognition=recognition,
                error_code="POSITION_SCOPE_MISMATCH",
                resolution_status=PositionResolutionStatus.SCOPE_MISMATCH,
            )
        if resolved.detection_status is PositionLabelDetectionStatus.DUPLICATE_POSITION_CODES:
            return CanonicalPositionValidationResult(
                status=CanonicalPositionValidationStatus.AMBIGUOUS_CODE,
                recognition=recognition,
                error_code="AMBIGUOUS_POSITION_IDENTIFIER",
                resolution_status=PositionResolutionStatus.ERROR,
            )
        return CanonicalPositionValidationResult(
            status=CanonicalPositionValidationStatus.FIELD_CONSTRAINT_VIOLATION,
            recognition=recognition,
            error_code="POSITION_NOT_ACTIVE",
            resolution_status=PositionResolutionStatus.INACTIVE,
        )

    @staticmethod
    def _unsigned_legacy_rejection(
        recognition: CanonicalPositionRecognition,
    ) -> CanonicalPositionValidationResult:
        return CanonicalPositionValidationResult(
            status=CanonicalPositionValidationStatus.SIGNATURE_REQUIRED_BY_LEGACY_POLICY,
            recognition=recognition,
            error_code="UNSIGNED_LEGACY_CATALOG_MISMATCH",
            policy_rejection=True,
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
        result = command.structural_result or self._labels.validate_best_effort(
            command.candidate,
            context=command.context,
        )
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
        *,
        record_operational_metrics: bool,
    ) -> CanonicalPositionValidationResult:
        if not record_operational_metrics:
            return result
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
