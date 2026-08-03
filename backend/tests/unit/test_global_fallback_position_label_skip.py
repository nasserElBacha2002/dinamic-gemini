"""Position-only CODE_SCAN outcomes must not force GLOBAL_EXTERNAL_FALLBACK."""

from __future__ import annotations

from src.application.services.image_processing.global_fallback_eligibility import (
    evaluate_global_fallback_eligibility,
)
from src.application.services.image_processing.global_fallback_merge_policy import (
    InternalAssetEvidence,
)


def test_position_label_only_assets_do_not_trigger_fallback_when_products_resolved() -> None:
    evidence = {
        "prod-1": InternalAssetEvidence(
            asset_id="prod-1",
            status="RESOLVED",
            internal_code="99090908898",
            quantity=999.0,
            resolved_internal=True,
        ),
        "prod-2": InternalAssetEvidence(
            asset_id="prod-2",
            status="RESOLVED",
            internal_code="22242925205",
            quantity=100000.0,
            resolved_internal=True,
        ),
        "pos-1": InternalAssetEvidence(
            asset_id="pos-1",
            status="UNRECOGNIZED",
            internal_code=None,
            quantity=None,
            resolved_internal=False,
            last_error_code="POSITION_LABEL_ONLY",
        ),
        "pos-2": InternalAssetEvidence(
            asset_id="pos-2",
            status="UNRECOGNIZED",
            internal_code=None,
            quantity=None,
            resolved_internal=False,
            last_error_code="POSITION_LABEL_ONLY",
        ),
    }
    decision = evaluate_global_fallback_eligibility(evidence)
    assert decision.needs_fallback is False
    assert decision.resolved_internal == 2
    assert decision.eligible_count == 0
