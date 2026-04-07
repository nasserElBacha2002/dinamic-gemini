"""Pipeline package. v2.2: single hybrid flow only."""

__all__ = ["HybridInventoryPipeline"]


def __getattr__(name: str):
    if name == "HybridInventoryPipeline":
        from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline

        return HybridInventoryPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
