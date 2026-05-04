"""
Contract tests for v3.0 application ports (Documento técnico §9.1, §9.2).

Verifies that stub implementations satisfy repository and service ABCs.
"""

from collections.abc import Sequence
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from src.application.ports.repositories import (
    AisleRepository,
    InventoryRepository,
)
from src.application.ports.services import (
    AnalysisProvider,
    ArtifactStorage,
    JobQueue,
    MetricsCalculator,
    ResultMapper,
)
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.inventory.entities import Inventory, InventoryStatus

# --- Repository stubs ---


class StubInventoryRepository(InventoryRepository):
    def __init__(self) -> None:
        self._store: dict[str, Inventory] = {}

    def save(self, inventory: Inventory) -> None:
        self._store[inventory.id] = inventory

    def get_by_id(self, inventory_id: str) -> Optional[Inventory]:
        return self._store.get(inventory_id)

    def list_all(self) -> Sequence[Inventory]:
        return list(self._store.values())


class StubAisleRepository(AisleRepository):
    def __init__(self) -> None:
        self._store: dict[str, Aisle] = {}

    def save(self, aisle: Aisle) -> None:
        self._store[aisle.id] = aisle

    def get_by_id(self, aisle_id: str) -> Optional[Aisle]:
        return self._store.get(aisle_id)

    def list_by_inventory(self, inventory_id: str) -> Sequence[Aisle]:
        return [a for a in self._store.values() if a.inventory_id == inventory_id]

    def get_by_inventory_and_code(self, inventory_id: str, code: str) -> Optional[Aisle]:
        for a in self._store.values():
            if a.inventory_id == inventory_id and a.code == code.strip():
                return a
        return None


def test_inventory_repository_contract() -> None:
    """Stub satisfies InventoryRepository: save, get_by_id, list_all."""
    repo: InventoryRepository = StubInventoryRepository()
    now = datetime(2025, 3, 6, 12, 0, 0)
    inv = Inventory(
        id="inv1",
        name="Test",
        status=InventoryStatus.DRAFT,
        created_at=now,
        updated_at=now,
    )
    repo.save(inv)
    assert repo.get_by_id("inv1") == inv
    assert list(repo.list_all()) == [inv]
    assert repo.get_by_id("nonexistent") is None


def test_aisle_repository_contract() -> None:
    """Stub satisfies AisleRepository: save, get_by_id, list_by_inventory."""
    repo: AisleRepository = StubAisleRepository()
    now = datetime(2025, 3, 6, 12, 0, 0)
    aisle = Aisle(
        id="a1",
        inventory_id="inv1",
        code="A01",
        status=AisleStatus.CREATED,
        created_at=now,
        updated_at=now,
    )
    repo.save(aisle)
    assert repo.get_by_id("a1") == aisle
    assert list(repo.list_by_inventory("inv1")) == [aisle]
    assert list(repo.list_by_inventory("other")) == []


# --- Service stubs ---


class StubArtifactStorage(ArtifactStorage):
    def save_file(self, path: str, file_obj: Any, content_type: str) -> str:
        return f"stub/{path}"

    def delete_file(self, path: str) -> None:
        pass


class StubJobQueue(JobQueue):
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


class StubAnalysisProvider(AnalysisProvider):
    def analyze_aisle(self, aisle_id: str, asset_paths: list[str]) -> dict[str, Any]:
        return {"positions": [], "aisle_id": aisle_id}


class StubMetricsCalculator(MetricsCalculator):
    def calculate_inventory_metrics(self, inventory_id: str) -> dict[str, Any]:
        return {
            "total_reviewed_positions": 0,
            "auto_accepted_positions": 0,
            "corrected_positions": 0,
            "deleted_positions": 0,
            "success_rate": 0.0,
        }


class StubResultMapper(ResultMapper):
    def map_analysis_to_positions(
        self, aisle_id: str, analysis_result: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return analysis_result.get("positions", [])


def test_artifact_storage_contract() -> None:
    """Stub satisfies ArtifactStorage: save_file returns path, delete_file exists."""
    storage: ArtifactStorage = StubArtifactStorage()
    path = storage.save_file("aisles/a1/raw/f1.jpg", BytesIO(b"x"), "image/jpeg")
    assert path == "stub/aisles/a1/raw/f1.jpg"
    storage.delete_file(path)


def test_job_queue_contract() -> None:
    """Stub satisfies JobQueue: enqueue accepts an existing job id."""
    stub = StubJobQueue()
    queue: JobQueue = stub
    queue.enqueue("job-1")
    assert stub.enqueued == ["job-1"]


def test_analysis_provider_contract() -> None:
    """Stub satisfies AnalysisProvider: analyze_aisle returns dict with positions."""
    provider: AnalysisProvider = StubAnalysisProvider()
    out = provider.analyze_aisle("a1", ["/path/to/1.jpg"])
    assert "positions" in out
    assert out["aisle_id"] == "a1"


def test_metrics_calculator_contract() -> None:
    """Stub satisfies MetricsCalculator: calculate_inventory_metrics returns metrics dict."""
    calc: MetricsCalculator = StubMetricsCalculator()
    m = calc.calculate_inventory_metrics("inv1")
    assert "total_reviewed_positions" in m
    assert "success_rate" in m


def test_result_mapper_contract() -> None:
    """Stub satisfies ResultMapper: map_analysis_to_positions returns list of position payloads."""
    mapper: ResultMapper = StubResultMapper()
    result = mapper.map_analysis_to_positions(
        "a1",
        {"positions": [{"id": "p1", "confidence": 0.9, "needs_review": False, "products": []}]},
    )
    assert len(result) == 1
    assert result[0]["id"] == "p1"
    assert result[0]["confidence"] == 0.9
