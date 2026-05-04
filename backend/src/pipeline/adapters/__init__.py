"""Pipeline adapters (Stage 2.3.B)."""

__all__ = ["HybridGlobalAnalysisStrategy"]


def __getattr__(name: str):
    if name == "HybridGlobalAnalysisStrategy":
        from src.pipeline.adapters.hybrid_global_analysis_strategy import (
            HybridGlobalAnalysisStrategy,
        )

        return HybridGlobalAnalysisStrategy
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
