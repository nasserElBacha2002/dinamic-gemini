from __future__ import annotations

from src.api.dependencies import (
    get_get_aisle_merge_results_use_case,
    get_run_aisle_merge_use_case,
)
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_final_count_repository import MemoryFinalCountRepository
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository


class _StubRecomputeUseCase:
    def execute(self, _command):  # pragma: no cover - wiring test only
        return None


def test_get_run_aisle_merge_use_case_uses_injected_recompute_dependency() -> None:
    uc = get_run_aisle_merge_use_case(
        inventory_repo=MemoryInventoryRepository(),
        aisle_repo=MemoryAisleRepository(),
        recompute_uc=_StubRecomputeUseCase(),
    )
    assert getattr(uc, "_recompute").__class__.__name__ == "_StubRecomputeUseCase"


def test_get_get_aisle_merge_results_use_case_uses_injected_final_count_repo() -> None:
    final_repo = MemoryFinalCountRepository()
    uc = get_get_aisle_merge_results_use_case(
        inventory_repo=MemoryInventoryRepository(),
        aisle_repo=MemoryAisleRepository(),
        final_count_repo=final_repo,
    )
    assert getattr(uc, "_final_count_repo") is final_repo

