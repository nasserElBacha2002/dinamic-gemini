from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from io import BytesIO

import pytest

from src.application.errors import (
    ClientNotFoundError,
    ClientSupplierClientMismatchError,
    ClientSupplierNotFoundError,
    EmptyUploadError,
    UnsupportedAssetTypeError,
    ZeroByteFileError,
)
from src.application.ports.repositories import (
    ClientRepository,
    ClientSupplierRepository,
    SupplierReferenceImageRepository,
)
from src.application.ports.services import ArtifactStorage
from src.application.use_cases.suppliers.upload_supplier_reference_images import (
    ListSupplierReferenceImagesUseCase,
    UploadedSupplierReferenceImageFile,
    UploadSupplierReferenceImagesUseCase,
)
from src.domain.client.entities import Client, ClientStatus
from src.domain.client_supplier.entities import ClientSupplier, ClientSupplierStatus
from src.domain.client_supplier.reference_image import SupplierReferenceImage
from src.infrastructure.storage.artifact_store import StoredArtifact


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


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
        if reference_image.id in self._store:
            raise ValueError("duplicate id")
        self._store[reference_image.id] = reference_image

    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        for image in reference_images:
            if image.id in self._store:
                raise ValueError("duplicate id")
        for image in reference_images:
            self._store[image.id] = image

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierReferenceImage]:
        rows = [
            image
            for image in self._store.values()
            if image.client_supplier_id == client_supplier_id
        ]
        rows.sort(key=lambda row: (row.created_at, row.id))
        return rows

    def delete(self, reference_image_id: str) -> None:
        self._store.pop(reference_image_id, None)


class StubArtifactStorage(ArtifactStorage):
    def __init__(self) -> None:
        self.written: list[tuple[str, bytes, str]] = []
        self.deleted: list[str] = []

    def save_file(self, path: str, file_obj: BytesIO, content_type: str) -> str:
        content = file_obj.read()
        self.written.append((path, content, content_type))
        return path

    def put_object(self, path: str, file_obj: BytesIO, content_type: str) -> StoredArtifact:
        content = file_obj.read()
        self.written.append((path, content, content_type))
        return StoredArtifact(
            storage_provider="s3",
            storage_bucket="bucket-supplier",
            storage_key=path,
            content_type=content_type,
            file_size_bytes=len(content),
            etag="etag-supplier",
        )

    def delete_file(self, path: str) -> None:
        self.deleted.append(path)


class FailingCreateManySupplierReferenceRepo(StubSupplierReferenceRepo):
    def create_many(self, reference_images: Sequence[SupplierReferenceImage]) -> None:
        raise RuntimeError("simulated db failure")


def _client(now: datetime) -> Client:
    return Client(
        id="cli-1",
        name="Cliente 1",
        status=ClientStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _supplier(now: datetime, client_id: str = "cli-1") -> ClientSupplier:
    return ClientSupplier(
        id="sup-1",
        client_id=client_id,
        name="Proveedor 1",
        status=ClientSupplierStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _build_upload_use_case(
    now: datetime,
    *,
    client_repo: StubClientRepo | None = None,
    supplier_repo: StubClientSupplierRepo | None = None,
    reference_repo: SupplierReferenceImageRepository | None = None,
    artifact_storage: StubArtifactStorage | None = None,
) -> UploadSupplierReferenceImagesUseCase:
    return UploadSupplierReferenceImagesUseCase(
        client_repo=client_repo or StubClientRepo(),
        client_supplier_repo=supplier_repo or StubClientSupplierRepo(),
        reference_repo=reference_repo or StubSupplierReferenceRepo(),
        artifact_storage=artifact_storage or StubArtifactStorage(),
        clock=FixedClock(now),
    )


def test_upload_supplier_reference_images_success() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    reference_repo = StubSupplierReferenceRepo()
    storage = StubArtifactStorage()
    use_case = _build_upload_use_case(
        now,
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=reference_repo,
        artifact_storage=storage,
    )

    files = [
        UploadedSupplierReferenceImageFile(
            original_filename="front.jpg",
            file_obj=BytesIO(b"front"),
            content_type="image/jpeg",
            size=5,
            label="Frente",
            description="Etiqueta frontal",
        )
    ]
    created = use_case.execute("cli-1", "sup-1", files)
    assert len(created) == 1
    assert created[0].client_supplier_id == "sup-1"
    assert created[0].storage_provider == "s3"
    assert created[0].label == "Frente"
    assert created[0].description == "Etiqueta frontal"
    assert created[0].storage_path.startswith("client_suppliers/sup-1/reference_images/")


def test_upload_supplier_reference_images_rejects_empty_upload() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    use_case = _build_upload_use_case(now)
    with pytest.raises(EmptyUploadError):
        use_case.execute("cli-1", "sup-1", [])


def test_upload_supplier_reference_images_rejects_missing_client() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    use_case = _build_upload_use_case(now, supplier_repo=supplier_repo)
    with pytest.raises(ClientNotFoundError):
        use_case.execute(
            "cli-unknown",
            "sup-1",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.jpg",
                    file_obj=BytesIO(b"front"),
                    content_type="image/jpeg",
                    size=5,
                )
            ],
        )


def test_upload_supplier_reference_images_rejects_missing_supplier() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    use_case = _build_upload_use_case(now, client_repo=client_repo)
    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute(
            "cli-1",
            "sup-missing",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.jpg",
                    file_obj=BytesIO(b"front"),
                    content_type="image/jpeg",
                    size=5,
                )
            ],
        )


def test_upload_supplier_reference_images_rejects_supplier_client_mismatch() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now, client_id="cli-other"))
    use_case = _build_upload_use_case(
        now, client_repo=client_repo, supplier_repo=supplier_repo
    )
    with pytest.raises(ClientSupplierClientMismatchError):
        use_case.execute(
            "cli-1",
            "sup-1",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.jpg",
                    file_obj=BytesIO(b"front"),
                    content_type="image/jpeg",
                    size=5,
                )
            ],
        )


def test_upload_supplier_reference_images_rejects_unsupported_mime() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    use_case = _build_upload_use_case(
        now, client_repo=client_repo, supplier_repo=supplier_repo
    )
    with pytest.raises(UnsupportedAssetTypeError):
        use_case.execute(
            "cli-1",
            "sup-1",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.pdf",
                    file_obj=BytesIO(b"pdf"),
                    content_type="application/pdf",
                    size=3,
                )
            ],
        )


def test_upload_supplier_reference_images_rejects_zero_byte_file() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    use_case = _build_upload_use_case(
        now, client_repo=client_repo, supplier_repo=supplier_repo
    )
    with pytest.raises(ZeroByteFileError):
        use_case.execute(
            "cli-1",
            "sup-1",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.jpg",
                    file_obj=BytesIO(b""),
                    content_type="image/jpeg",
                    size=0,
                )
            ],
        )


def test_upload_supplier_reference_images_rolls_back_written_files_on_db_failure() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    storage = StubArtifactStorage()
    use_case = _build_upload_use_case(
        now,
        client_repo=client_repo,
        supplier_repo=supplier_repo,
        reference_repo=FailingCreateManySupplierReferenceRepo(),
        artifact_storage=storage,
    )
    with pytest.raises(RuntimeError, match="simulated db failure"):
        use_case.execute(
            "cli-1",
            "sup-1",
            [
                UploadedSupplierReferenceImageFile(
                    original_filename="front.jpg",
                    file_obj=BytesIO(b"front"),
                    content_type="image/jpeg",
                    size=5,
                ),
                UploadedSupplierReferenceImageFile(
                    original_filename="side.png",
                    file_obj=BytesIO(b"side"),
                    content_type="image/png",
                    size=4,
                ),
            ],
        )
    written_paths = [row[0] for row in storage.written]
    assert storage.deleted == list(reversed(written_paths))


def test_list_supplier_reference_images_validates_scope_and_returns_rows() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    reference_repo = StubSupplierReferenceRepo()
    reference_repo.create(
        SupplierReferenceImage(
            id="img-1",
            client_supplier_id="sup-1",
            filename="front.jpg",
            storage_path="client_suppliers/sup-1/reference_images/img-1.jpg",
            mime_type="image/jpeg",
            file_size=5,
            created_at=now,
            updated_at=now,
        )
    )
    use_case = ListSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        reference_repo=reference_repo,
    )
    listed = use_case.execute("cli-1", "sup-1")
    assert [row.id for row in listed] == ["img-1"]


def test_list_supplier_reference_images_rejects_missing_client() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now))
    use_case = ListSupplierReferenceImagesUseCase(
        client_repo=StubClientRepo(),
        client_supplier_repo=supplier_repo,
        reference_repo=StubSupplierReferenceRepo(),
    )
    with pytest.raises(ClientNotFoundError):
        use_case.execute("cli-missing", "sup-1")


def test_list_supplier_reference_images_rejects_missing_supplier() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    use_case = ListSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=StubClientSupplierRepo(),
        reference_repo=StubSupplierReferenceRepo(),
    )
    with pytest.raises(ClientSupplierNotFoundError):
        use_case.execute("cli-1", "sup-missing")


def test_list_supplier_reference_images_rejects_supplier_client_mismatch() -> None:
    now = datetime(2026, 5, 7, 12, 0, 0, tzinfo=timezone.utc)
    client_repo = StubClientRepo()
    client_repo.save(_client(now))
    supplier_repo = StubClientSupplierRepo()
    supplier_repo.save(_supplier(now, client_id="cli-other"))
    use_case = ListSupplierReferenceImagesUseCase(
        client_repo=client_repo,
        client_supplier_repo=supplier_repo,
        reference_repo=StubSupplierReferenceRepo(),
    )
    with pytest.raises(ClientSupplierClientMismatchError):
        use_case.execute("cli-1", "sup-1")
