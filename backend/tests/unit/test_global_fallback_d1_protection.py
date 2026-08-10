"""GLOBAL_EXTERNAL_FALLBACK must not invent products after invalid D1 labels."""

from __future__ import annotations

from src.application.services.image_processing.global_fallback_eligibility import (
    FALLBACK_SKIP_ERROR_CODES,
    evaluate_global_fallback_eligibility,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    InternalAssetEvidence,
)


def test_d1_candidates_failed_skips_global_fallback() -> None:
    assert "D1_CANDIDATES_FAILED" in FALLBACK_SKIP_ERROR_CODES
    evidence = {
        "a1": InternalAssetEvidence(
            asset_id="a1",
            status="UNRECOGNIZED",
            resolved_internal=False,
            internal_code=None,
            quantity=None,
            last_error_code="D1_CANDIDATES_FAILED",
        )
    }
    decision = evaluate_global_fallback_eligibility(evidence)
    assert decision.needs_fallback is False


def test_no_code_symbol_still_eligible_for_fallback() -> None:
    evidence = {
        "a1": InternalAssetEvidence(
            asset_id="a1",
            status="UNRECOGNIZED",
            resolved_internal=False,
            internal_code=None,
            quantity=None,
            last_error_code="NO_CODE_SYMBOL_FOUND",
        )
    }
    decision = evaluate_global_fallback_eligibility(evidence)
    assert decision.needs_fallback is True


def test_mixed_aisle_d1_failed_not_apply_external() -> None:
    """Peer eligible for GLOBAL_BATCH must not resurrect a hard-rejected D1 asset."""
    from src.application.services.image_processing.global_fallback_merge_planner import (
        build_merge_plan,
    )
    from src.application.services.image_processing.global_fallback_merge_policy import (
        ExternalEntityEvidence,
        GlobalFallbackMergeAction,
        decide_merge_for_asset,
    )

    evidence = {
        "d1-fail": InternalAssetEvidence(
            asset_id="d1-fail",
            status="UNRECOGNIZED",
            resolved_internal=False,
            internal_code=None,
            quantity=None,
            last_error_code="D1_CANDIDATES_FAILED",
        ),
        "no-code": InternalAssetEvidence(
            asset_id="no-code",
            status="UNRECOGNIZED",
            resolved_internal=False,
            internal_code=None,
            quantity=None,
            last_error_code="NO_CODE_SYMBOL_FOUND",
        ),
    }
    assert evaluate_global_fallback_eligibility(evidence).needs_fallback is True

    decision = decide_merge_for_asset(
        internal=evidence["d1-fail"],
        external=ExternalEntityEvidence(
            internal_code="INVENTED",
            quantity=999.0,
            source_image_id="d1-fail",
        ),
    )
    assert decision.action is GlobalFallbackMergeAction.KEEP_INTERNAL
    assert "hard_reject" in decision.reason

    plan = build_merge_plan(
        batch_fingerprint="fp",
        entities=[
            {
                "internal_code": "INVENTED",
                "quantity": 999,
                "source_image_id": "d1-fail",
            },
            {
                "internal_code": "REAL",
                "quantity": 1,
                "source_image_id": "no-code",
            },
        ],
        evidence_by_asset=evidence,
        ordered_asset_ids=["d1-fail", "no-code"],
    )
    applied_assets = {
        op.decision.asset_id
        for op in plan.operations
        if op.decision.action
        in (GlobalFallbackMergeAction.APPLY_EXTERNAL, GlobalFallbackMergeAction.COMBINE_QUANTITY)
    }
    assert "d1-fail" not in applied_assets
    assert "no-code" in applied_assets
