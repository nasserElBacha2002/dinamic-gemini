"""Phase 5 — estimate monetary cost for one external fallback call (informational)."""

from __future__ import annotations

from typing import Any

from src.llm.costing import build_llm_cost_snapshot


class ExternalCostEstimator:
    """Wraps the shared LLM cost snapshot; returns null when usage/pricing is unavailable."""

    def estimate(
        self,
        *,
        provider: str,
        model: str | None,
        usage: dict[str, Any] | None,
        settings: Any,
    ) -> float | None:
        if not usage:
            return None
        try:
            snapshot = build_llm_cost_snapshot(
                provider=provider,
                model=model,
                raw_usage=usage,
                settings=settings,
            )
        except Exception:
            return None
        total = snapshot.get("total_cost")
        if total is None:
            total = snapshot.get("partial_total_cost")
        if total is None:
            return None
        try:
            return float(total)
        except (TypeError, ValueError):
            return None


__all__ = ["ExternalCostEstimator"]
