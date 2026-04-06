"""Pipeline adapters (Stage 2.3.B)."""

__all__ = ["GeminiAnalysisProvider"]


def __getattr__(name: str):
    if name == "GeminiAnalysisProvider":
        from src.pipeline.adapters.gemini_analysis_provider import GeminiAnalysisProvider

        return GeminiAnalysisProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
