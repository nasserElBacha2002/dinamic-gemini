"""Phase 6 corrections — shared validator, snapshot, recovery, sources, decimals."""

from __future__ import annotations

import pytest

from src.application.services.image_processing.external_fallback_recovery import (
    ExternalFallbackRecoveryService,
)
from src.application.services.image_processing.extraction_profile_configuration import (
    ExtractionProfileConfigurationError,
    parse_extraction_configuration,
)
from src.application.services.image_processing.field_candidate_set import (
    FieldCandidateSet,
    apply_profile_validation,
)
from src.application.services.image_processing.profile_aware_processing_result_validator import (
    FieldCandidate,
    ProfileAwareProcessingResultValidator,
)
from src.application.services.image_processing.supplier_extraction_profile_resolver import (
    ProfileSnapshotInvalidError,
    SupplierExtractionProfileResolver,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    InternalCodeSourceRule,
    QuantityExtractionRules,
    default_extraction_configuration,
)
from src.domain.image_processing.contracts import ImageResultStatus
from src.domain.image_processing.external_image_analysis_request import (
    ExternalImageAnalysisRequest,
    ExternalRequestStatus,
)


def _strict_ean_only() -> ExtractionProfileConfiguration:
    return ExtractionProfileConfiguration(
        internal_code_sources=(
            InternalCodeSourceRule("EAN", priority=1, enabled=True, requires_label=False),
        ),
        forbidden_internal_code_sources=("ARTICLE",),
        quantity_rules=QuantityExtractionRules(allow_decimals=False),
        allow_unconfigured_code_source_fallback=False,
    )


def test_unconfigured_source_ignored_no_permissive_fallback() -> None:
    validator = ProfileAwareProcessingResultValidator(_strict_ean_only())
    result = validator.validate_resolved(
        code_candidates=[
            FieldCandidate(source_key="ARTICLE", value="ART-1", labeled=True),
        ],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="12")],
    )
    assert not result.ok
    assert "MISSING_INTERNAL_CODE" in result.errors


def test_requires_label_filters_bare_ean() -> None:
    config = ExtractionProfileConfiguration(
        internal_code_sources=(
            InternalCodeSourceRule("EAN", priority=1, requires_label=True),
        ),
        allow_unconfigured_code_source_fallback=False,
    )
    validator = ProfileAwareProcessingResultValidator(config)
    bare = validator.validate_resolved(
        code_candidates=[
            FieldCandidate(source_key="EAN", value="5901234123457", labeled=False),
        ],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="3")],
    )
    assert not bare.ok
    labeled = validator.validate_resolved(
        code_candidates=[
            FieldCandidate(source_key="EAN", value="5901234123457", labeled=True),
        ],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="3")],
    )
    assert labeled.ok
    assert labeled.internal_code == "5901234123457"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12", 12),
        ("12.0", 12),
        ("12,0", 12),
        ("12.5", None),
        ("12,5", None),
    ],
)
def test_quantity_integer_only_no_float_truncation(raw: str, expected: int | None) -> None:
    validator = ProfileAwareProcessingResultValidator(default_extraction_configuration())
    parsed = validator._parse_quantity(raw)
    assert parsed == expected


def test_regex_rejected_at_parse() -> None:
    with pytest.raises(ExtractionProfileConfigurationError) as exc:
        parse_extraction_configuration(
            {
                "internal_code_sources": [
                    {"field_key": "EAN", "priority": 1, "enabled": True}
                ],
                "validation_rules": {"code": {"regex": "a+"}},
            }
        )
    assert exc.value.code == "REGEX_NOT_SUPPORTED"


def test_invalid_snapshot_raises_not_active_fallback() -> None:
    resolver = SupplierExtractionProfileResolver(profiles_enabled=True)
    with pytest.raises(ProfileSnapshotInvalidError):
        resolver.resolve_for_job(
            client_id="c1",
            supplier_id="s1",
            engine_params={
                "identification_execution": {
                    "supplier_extraction_profile": {
                        "configuration": {"internal_code_sources": "bad"},
                    }
                }
            },
        )


def test_historical_job_without_profile_key_is_legacy_compat() -> None:
    resolver = SupplierExtractionProfileResolver(profiles_enabled=True)
    resolved = resolver.resolve_for_job(
        client_id="c1",
        supplier_id="s1",
        engine_params={"identification_execution": {"executed_strategy": "CODE_SCAN"}},
    )
    assert resolved.source == "LEGACY_COMPAT"


def test_persisted_without_position_reconciles() -> None:
    from datetime import datetime, timezone

    svc = ExternalFallbackRecoveryService()
    now = datetime.now(timezone.utc)
    req = ExternalImageAnalysisRequest(
        id="r1",
        idempotency_key="k",
        job_id="j",
        asset_id="a",
        provider="gemini",
        model="m",
        prompt_key="p",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.PERSISTED,
        worker_token="w",
        created_at=now,
        updated_at=now,
        position_id=None,
        active_result_id=None,
        normalized_result={"internal_code": "X", "quantity": 1},
    )
    decision = svc.decide(req)
    assert decision.action == "RECONCILE_PERSISTED"


def test_persisted_with_position_skips() -> None:
    from datetime import datetime, timezone

    svc = ExternalFallbackRecoveryService()
    now = datetime.now(timezone.utc)
    req = ExternalImageAnalysisRequest(
        id="r1",
        idempotency_key="k",
        job_id="j",
        asset_id="a",
        provider="gemini",
        model="m",
        prompt_key="p",
        prompt_version="1",
        configuration_snapshot_version=1,
        status=ExternalRequestStatus.PERSISTED,
        worker_token="w",
        created_at=now,
        updated_at=now,
        position_id="pos-1",
    )
    assert svc.decide(req).action == "SKIP_PERSISTED"


def test_same_profile_apply_validation_produces_resolved() -> None:
    config = default_extraction_configuration()
    candidates = FieldCandidateSet(
        code_candidates=[
            FieldCandidate(source_key="INTERNAL_CODE", value="ABC", labeled=True)
        ],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="12")],
    )
    result = apply_profile_validation(
        job_id="j",
        asset_id="a",
        processing_mode="CODE_SCAN",
        resolved_by="CODE_SCAN",
        candidates=candidates,
        configuration=config,
    )
    assert result.status is ImageResultStatus.RESOLVED_INTERNAL
    assert result.evidence and result.evidence.get("profile_validation_executed") is True


def test_ean_checksum_invalid() -> None:
    validator = ProfileAwareProcessingResultValidator(_strict_ean_only())
    result = validator.validate_resolved(
        code_candidates=[
            FieldCandidate(source_key="EAN", value="1234567890123", labeled=True)
        ],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="1")],
    )
    assert "INVALID_EAN_CHECKSUM" in result.errors


def test_default_allows_unconfigured_fallback() -> None:
    validator = ProfileAwareProcessingResultValidator(default_extraction_configuration())
    # SKU is configured in default? default has INTERNAL_CODE, EAN, ARTICLE — not SKU
    # with allow_unconfigured_code_source_fallback=True, SKU should still work via fallback
    result = validator.validate_resolved(
        code_candidates=[FieldCandidate(source_key="SKU", value="SKU-9", labeled=True)],
        quantity_candidates=[FieldCandidate(source_key="QUANTITY", value="2")],
    )
    assert result.ok
    assert result.internal_code == "SKU-9"
