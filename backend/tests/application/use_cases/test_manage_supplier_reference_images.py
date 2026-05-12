from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    SupplierReferenceImageNotFoundError,
)
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.use_cases.manage_supplier_reference_images import (
    DeleteSupplierReferenceImageUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.reference_image import SupplierReferenceImage


class StubClientRepo(ClientRepository):
    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[client.id] = client

    def get_by_id(self, client_id: str) -> Client | None:
        return self._store.get(client_id)

    def list_all(self) -> Sequence[Client]:
        return list(self._store.values())


class StubClientSupplierRepo(ClientSupplierRepository):
    def __init__(self) -> None:
        self._store: dict[str, ClientSupplier] = {}

    def save(self, supplier: ClientSupplier) -> None:
        self._store[supplier.id] = supplier

    def get_by_id(self, supplier_id: str) -> ClientSupplier | None:
        return self._store.get(supplier_id)

    def get_by_client_and_name(self, client_id: str, name: str) -> ClientSupplier | None:
        for supplier in self._store.values():
            if supplier.client_id == client_id and supplier.name == name:
                return supplier
        return None

    def list_by_client(self, client_id: str) -> Sequence[ClientSupplier]:
        return [supplier for supplier in self._store.values() if supplier.client_id == client_id]


class StubSupplierReferenceRepo(SupplierReferenceImageRepository):
    def __init__(self) -> None:
        self._store: dict[str, SupplierReferenceImage] = {}

    def get_by_id(self, reference_image_id: str) -> SupplierReferenceImage | None:
        return self._store.get(reference_image_id)

    def create(self, reference_image: SupplierReferenceImage) -> None:
        self._store[reference_image.id] = reference_image

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        for image in reference_images:
            self._store[image.id] = image

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        return [
            image
            for image in self._store.values()
            if image.client_supplier_id == client_supplier_id
        ]

    def delete(self, reference_image_id: str) -> None:
        self._store.pop(reference_image_id, None)


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def save_file(self, path, file_obj, content_type):  # pragma: no cover - not used in this test
        return path

    def delete_file(self, path: str) -> None:
        self.deleted.append(path)


class FailingDeleteArtifactStorage(StubArtifactStorage):
    def delete_file(self, path: str) -> None:
        self.deleted.append(path)
        raise RuntimeError("simulated storage delete failure")


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)


def _client() -> Client:
    now = _now()
    return Client(
        id="cli-1",
        name="Cliente",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _supplier(*, client_id: str = "cli-1") -> ClientSupplier:
    now = _now()
    return ClientSupplier(
        id="sup-1",
        client_id=client_id,
        name="Proveedor",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _image(*, supplier_id: str = "sup-1") -> SupplierReferenceImage:
    now = _now()
    return SupplierReferenceImage(
        id="img-1",
        client_supplier_id=supplier_id,
        filename="front.jpg",
        storage_path=f"client_suppliers/{supplier_id}/reference_images/img-1.jpg",
        storage_key=f"client_suppliers/{supplier_id}/reference_images/img-1.jpg",
        mime_type="image/jpeg",
        file_size=5,
        created_at=now,
        updated_at=now,
    )


def _build_use_case(
    *,
    client_repo: StubClientRepo | None = None,
    supplier_repo: StubClientSupplierRepo | None = None,
    reference_repo: StubSupplierReferenceRepo | None = None,
    storage: StubArtifactStorage | None = None,
) -> DeleteSupplierReferenceImageUseCase:
    return DeleteSupplierReferenceImageUseCase(
        client_repo=client_repo or StubClientRepo(),
        client_supplier_repo=supplier_repo or StubClientSupplierRepo(),
        reference_repo=reference_repo or StubSupplierReferenceRepo(),
        artifact_storage=storage or StubArtifactStorage(),
    )


def test_delete_supplier_reference_image_success() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(_image())
    storage = StubArtifactStorage()
    use_case = _build_use_case(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=reference_repo,
        storage=storage,
    )
    use_case.execute("cli-1", "sup-1", "img-1")
    assert reference_repo.get_by_id("img-1") is None
    assert storage.deleted == ["client_suppliers/sup-1/reference_images/img-1.jpg"]


def test_delete_supplier_reference_image_rejects_missing_client() -> None:
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(_image())
    use_case = _build_use_case(supplier_repo=supplier_repo, reference_repo=reference_repo)
    with pytest.raises(ClientNotFoundError):
        use_case.execute("cli-missing", "sup-1", "img-1")


def test_delete_supplier_reference_image_rejects_missing_supplier() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    use_case = _build_use_case(client_repo=client_repo)
    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute("cli-1", "sup-missing", "img-1")


def test_delete_supplier_reference_image_rejects_supplier_client_mismatch() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(client_id="cli-other"))
    use_case = _build_use_case(client_repo=client_repo, supplier_repo=supplier_repo)
    with pytest.raises(ClientSupplierClientMismatchError):
        use_case.execute("cli-1", "sup-1", "img-1")


def test_delete_supplier_reference_image_rejects_missing_image() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    use_case = _build_use_case(client_repo=client_repo, supplier_repo=supplier_repo)
    with pytest.raises(SupplierReferenceImageNotFoundError):
        use_case.execute("cli-1", "sup-1", "img-missing")


def test_delete_supplier_reference_image_rejects_image_from_another_supplier() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(_image(supplier_id="sup-other"))
    use_case = _build_use_case(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=reference_repo,
    )
    with pytest.raises(SupplierReferenceImageNotFoundError):
        use_case.execute("cli-1", "sup-1", "img-1")


def test_delete_supplier_reference_image_falls_back_to_storage_path_when_key_is_missing() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(
        SupplierReferenceImage(
            id="img-1",
            client_supplier_id="sup-1",
            filename="front.jpg",
            storage_path="client_suppliers/sup-1/reference_images/img-1.jpg",
            storage_key=None,
            mime_type="image/jpeg",
            file_size=5,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    storage = StubArtifactStorage()
    use_case = _build_use_case(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=reference_repo,
        storage=storage,
    )
    use_case.execute("cli-1", "sup-1", "img-1")
    assert reference_repo.get_by_id("img-1") is None
    assert storage.deleted == ["client_suppliers/sup-1/reference_images/img-1.jpg"]


def test_delete_supplier_reference_image_keeps_db_delete_when_cleanup_fails() -> None:
    client_repo = StubClientRepo()
    client_repo.save(_client())
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier())
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(_image())
    storage = FailingDeleteArtifactStorage()
    use_case = _build_use_case(
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=reference_repo,
        storage=storage,
    )
    use_case.execute("cli-1", "sup-1", "img-1")
    assert reference_repo.get_by_id("img-1") is None
    assert storage.deleted == ["client_suppliers/sup-1/reference_images/img-1.jpg"]
