"""HTTP integration tests: hierarchical auth BEFORE staging spool (Phase 2 correction).

Covers ``POST .../capture-sessions/{session_id}/items`` (and, for the aisle-asset upload
endpoint, ``POST .../aisles/{aisle_id}/assets``) via a real ``TestClient`` — not just the
use-case unit tests already in ``tests/application/use_cases``.

**Real FastAPI behavior verified for this module (do not assume otherwise):**

- ``principal: AccessPrincipal = Depends(require_capture_session_upload_scope)`` /
  ``Depends(require_inventory_client_scope)`` is declared *before* ``files: list[UploadFile]
  = File(...)`` in the route signature. FastAPI resolves a route's dependency tree and its
  ``File(...)``/``Form(...)`` body parameters together in a single ``solve_dependencies``
  pass ahead of the route body. That pass **does** let Starlette bind the incoming multipart
  parts into ``UploadFile`` objects — declaration order does not, by itself, stop Starlette
  from parsing multipart at the ASGI layer. Do **not** claim "the body is never parsed" — it
  is not accurate to this codebase.
- What *is* guaranteed, and what every "deny" test below asserts, is that the
  **application-level spool step** — ``_upload_files_to_staging_dtos`` (capture sessions) /
  ``read_uploaded_files_for_aisle_asset_upload`` (aisle assets), which stream each
  ``UploadFile`` to a new spooled temp file, apply size limits, and produce the
  ``UploadedFile`` DTOs the use case persists from — never executes when the auth dependency
  raises. Nor does the use case's own artifact-storage write or repository ``save()``. The
  route body (where all of those calls live) is only entered once every dependency —
  including the auth dependency — has resolved without raising.
- ``require_capture_session_upload_scope`` / ``require_inventory_client_scope`` are FastAPI
  **dependencies**, not route-body code, so a route's own ``try/except: reraise_if_mapped(e)``
  cannot see exceptions raised while resolving them. ``backend/src/api/dependencies.py`` maps
  ``InventoryNotFoundError`` / ``AisleNotFoundError`` / ``CaptureSessionNotFoundError`` to
  ``StructuredApiHttpError`` (404) *inside* those dependency functions for exactly this reason
  — an unmapped domain error raised there would otherwise escape every registered exception
  handler except the generic ``Exception`` handler and surface as a 500.

Every test in this module overrides only ``get_current_admin`` and the repository/storage
dependencies (with in-memory implementations) so the *real* ``require_capture_session_upload_scope``
/ ``require_inventory_client_scope`` dependency code runs unmodified — this file does not
override those dependency functions themselves.

**Asymmetry between the two routes (documented, not a test bug):** the capture-session upload
dependency (``require_capture_session_upload_scope``) validates the *full* inventory→aisle→
session hierarchy before the route body runs, so every capture-session cross-hierarchy case
below has spool calls == 0. The aisle asset upload dependency (``require_inventory_client_scope``)
only validates actor→client→inventory scope; inventory→aisle ownership is checked by
``UploadAisleAssetsUseCase`` itself (defense-in-depth, before any storage write, but after the
route has already spooled multipart parts). That single case therefore asserts spool calls == 1
and storage/DB writes == 0, and is called out explicitly in its test docstring.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

import src.api.routes.v3.assets as assets_routes
import src.api.routes.v3.capture_sessions as capture_sessions_routes
from src.api.dependencies import (
    get_artifact_storage,
    get_upload_aisle_assets_use_case,
    get_upload_capture_session_staging_items_use_case,
)
from src.api.errors.structured_api_http import (
    AISLE_NOT_FOUND,
    CAPTURE_SESSION_NOT_FOUND,
    INVENTORY_NOT_FOUND,
)
from src.api.server import app
from src.application.use_cases.aisles.upload_aisle_assets import AisleAssetUploadBatchResult
from src.application.use_cases.capture_sessions.upload_capture_session_staging_items import (
    StagingUploadBatchResult,
)
from src.auth.dependencies import get_current_admin
from src.auth.schemas import AuthUser
from src.domain.aisle.entities import Aisle, AisleStatus
from src.domain.capture.entities import CaptureSession, CaptureSessionStatus
from src.domain.inventory.entities import Inventory, InventoryStatus
from src.infrastructure.repositories.memory_aisle_repository import MemoryAisleRepository
from src.infrastructure.repositories.memory_capture_session_item_repository import (
    MemoryCaptureSessionItemRepository,
)
from src.infrastructure.repositories.memory_capture_session_repository import (
    MemoryCaptureSessionRepository,
)
from src.infrastructure.repositories.memory_inventory_repository import MemoryInventoryRepository
from src.infrastructure.repositories.memory_source_asset_repository import (
    MemorySourceAssetRepository,
)
from src.runtime.v3_deps import (
    get_aisle_repo,
    get_capture_session_item_repo,
    get_capture_session_repo,
    get_inventory_repo,
    get_source_asset_repo,
)

_NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)
_ONE_FILE = [("files", ("evidence.jpg", b"fake-jpeg-bytes", "image/jpeg"))]


def _inventory(inv_id: str, *, client_id: str | None) -> Inventory:
    return Inventory(
        id=inv_id,
        name=f"Inventory {inv_id}",
        status=InventoryStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
        client_id=client_id,
    )


def _aisle(aisle_id: str, *, inventory_id: str) -> Aisle:
    return Aisle(
        id=aisle_id,
        inventory_id=inventory_id,
        code=f"CODE-{aisle_id}",
        status=AisleStatus.CREATED,
        created_at=_NOW,
        updated_at=_NOW,
        is_active=True,
    )


def _session(
    session_id: str, *, inventory_id: str, aisle_id: str | None = None
) -> CaptureSession:
    return CaptureSession(
        id=session_id,
        inventory_id=inventory_id,
        aisle_id=aisle_id,
        status=CaptureSessionStatus.DRAFT,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _platform_admin() -> AuthUser:
    return AuthUser(id="u-platform", username="platform", role="platform_admin")


def _company_admin(client_id: str) -> AuthUser:
    return AuthUser(id="u-company", username="company", role="company_admin", client_id=client_id)


class _CallCounter:
    """Counts invocations of a wrapped callable (sync or async)."""

    def __init__(self) -> None:
        self.count = 0


def _wrap_async_call_counter(
    monkeypatch: pytest.MonkeyPatch, module: Any, attr_name: str
) -> _CallCounter:
    counter = _CallCounter()
    original: Callable[..., Any] = getattr(module, attr_name)

    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        counter.count += 1
        return await original(*args, **kwargs)

    monkeypatch.setattr(module, attr_name, _wrapped)
    return counter


class _CountingArtifactStorage:
    """Minimal ``ArtifactStorage`` stub that records ``save_file``/``delete_file`` calls."""

    def __init__(self) -> None:
        self.save_calls = 0
        self.delete_calls = 0

    def save_file(self, key: str, data: Any, content_type: str | None = None) -> str:
        self.save_calls += 1
        return key

    def delete_file(self, key: str) -> None:
        self.delete_calls += 1


class _StubUploadCaptureSessionUseCase:
    """Records ``execute`` calls and returns an empty successful batch (auth already ran)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> StagingUploadBatchResult:
        self.calls.append(kwargs)
        return StagingUploadBatchResult(items=(), errors=())


class _StubUploadAisleAssetsUseCase:
    """Records ``execute`` calls and returns an empty successful batch (auth already ran)."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def execute(self, *args: Any, **kwargs: Any) -> AisleAssetUploadBatchResult:
        self.calls.append((args, kwargs))
        return AisleAssetUploadBatchResult(upload_batch_id=None, assets=[], errors=[])


class _Repos:
    def __init__(self) -> None:
        self.inventory = MemoryInventoryRepository()
        self.aisle = MemoryAisleRepository()
        self.session = MemoryCaptureSessionRepository()
        self.item = MemoryCaptureSessionItemRepository()
        self.source_asset = MemorySourceAssetRepository()


@pytest.fixture
def repos() -> _Repos:
    return _Repos()


@pytest.fixture
def storage() -> _CountingArtifactStorage:
    return _CountingArtifactStorage()


@pytest.fixture
def api_client(repos: _Repos, storage: _CountingArtifactStorage):
    """Real ``TestClient`` with only auth + repos + storage overridden (real access-policy code runs)."""
    overrides = {
        get_inventory_repo: lambda: repos.inventory,
        get_aisle_repo: lambda: repos.aisle,
        get_capture_session_repo: lambda: repos.session,
        get_capture_session_item_repo: lambda: repos.item,
        get_source_asset_repo: lambda: repos.source_asset,
        get_artifact_storage: lambda: storage,
    }
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app)
    finally:
        for dep in overrides:
            app.dependency_overrides.pop(dep, None)


def _set_admin(user: AuthUser) -> None:
    app.dependency_overrides[get_current_admin] = lambda: user


def _clear_admin() -> None:
    app.dependency_overrides.pop(get_current_admin, None)


# ---------------------------------------------------------------------------
# Capture session staging upload: cross-hierarchy denials before spool.
# ---------------------------------------------------------------------------


def test_session_belongs_to_other_inventory_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Inventory A + a session that actually belongs to inventory B → 404, zero spool/storage/DB writes."""
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.inventory.save(_inventory("inv-b", client_id=None))
    repos.session.save(_session("session-b", inventory_id="inv-b"))
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/capture-sessions/session-b/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == CAPTURE_SESSION_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert repos.item.list_by_session("session-b") == ()


def test_aisle_belongs_to_other_inventory_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Inventory A + an aisle_id that actually belongs to inventory B → 404 aisle-not-found, zero spool."""
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.inventory.save(_inventory("inv-b", client_id=None))
    repos.aisle.save(_aisle("aisle-b", inventory_id="inv-b"))
    repos.session.save(_session("session-a", inventory_id="inv-a"))
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/aisles/aisle-b/capture-sessions/session-a/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == AISLE_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert repos.item.list_by_session("session-a") == ()


def test_session_and_aisle_mismatch_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Same inventory, but the session is scoped to aisle A while the request names aisle B → 404, zero spool."""
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.aisle.save(_aisle("aisle-a", inventory_id="inv-a"))
    repos.aisle.save(_aisle("aisle-b", inventory_id="inv-a"))
    repos.session.save(_session("session-a", inventory_id="inv-a", aisle_id="aisle-a"))
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/aisles/aisle-b/capture-sessions/session-a/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == CAPTURE_SESSION_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert repos.item.list_by_session("session-a") == ()


def test_nonexistent_session_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """A valid inventory but a session id that was never created → 404, zero spool/storage/DB writes."""
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/capture-sessions/does-not-exist/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == CAPTURE_SESSION_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert repos.item.list_by_session("does-not-exist") == ()


def test_company_actor_cross_client_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Company admin for client X hitting an inventory owned by client Y → 404, zero spool, before session lookup."""
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id="client-y"))
    repos.session.save(_session("session-a", inventory_id="inv-a"))
    _set_admin(_company_admin("client-x"))
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/capture-sessions/session-a/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == INVENTORY_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert repos.item.list_by_session("session-a") == ()


def test_platform_actor_succeeds_after_auth_and_spool_runs(
    api_client: TestClient, repos: _Repos, monkeypatch
) -> None:
    """Positive control: a valid session for a platform actor passes auth and the route body runs.

    Contrasts with the deny tests above — spool (and the use case) run exactly once here,
    confirming the counter/mocks would have caught a false "always zero" assertion.
    """
    counter = _wrap_async_call_counter(
        monkeypatch, capture_sessions_routes, "_upload_files_to_staging_dtos"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.session.save(_session("session-a", inventory_id="inv-a"))
    stub_use_case = _StubUploadCaptureSessionUseCase()
    app.dependency_overrides[get_upload_capture_session_staging_items_use_case] = (
        lambda: stub_use_case
    )
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/capture-sessions/session-a/items",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()
        app.dependency_overrides.pop(get_upload_capture_session_staging_items_use_case, None)

    assert resp.status_code == 201, resp.text
    assert counter.count == 1
    assert len(stub_use_case.calls) == 1
    assert stub_use_case.calls[0]["principal"].is_platform is True


# ---------------------------------------------------------------------------
# Aisle asset upload: cross-hierarchy denials before spool (API layer, not just use-case unit tests).
# ---------------------------------------------------------------------------


def test_aisle_asset_upload_cross_client_denies_before_spool(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Company admin for client X uploading assets to an aisle under client Y's inventory → 404, zero spool."""
    counter = _wrap_async_call_counter(
        monkeypatch, assets_routes, "read_uploaded_files_for_aisle_asset_upload"
    )
    repos.inventory.save(_inventory("inv-a", client_id="client-y"))
    repos.aisle.save(_aisle("aisle-a", inventory_id="inv-a"))
    _set_admin(_company_admin("client-x"))
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/aisles/aisle-a/assets",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == INVENTORY_NOT_FOUND
    assert counter.count == 0
    assert storage.save_calls == 0
    assert list(repos.source_asset.list_by_aisle("aisle-a")) == []


def test_aisle_asset_upload_aisle_belongs_to_other_inventory_denies_before_storage(
    api_client: TestClient, repos: _Repos, storage: _CountingArtifactStorage, monkeypatch
) -> None:
    """Inventory A path with an aisle_id that actually belongs to inventory B → 404, zero storage/DB writes.

    **Documented finding (not a test bug):** unlike the capture-session upload routes, the aisle
    asset upload route's pre-spool dependency (``require_inventory_client_scope``) only enforces
    actor→client→inventory scope — it does not check inventory→aisle ownership. That check is
    defense-in-depth inside ``UploadAisleAssetsUseCase.execute`` (``access_policy.require_aisle``,
    called "before any storage writes" per its own inline comment), which runs *after* the route
    has already spooled the multipart parts into ``UploadedFile`` DTOs. So this specific
    cross-hierarchy case has ``spool calls == 1`` (not 0) while still guaranteeing zero storage
    writes and zero persisted rows. See ``audit-results/phase-2/upload-authorization-matrix.md``.
    """
    counter = _wrap_async_call_counter(
        monkeypatch, assets_routes, "read_uploaded_files_for_aisle_asset_upload"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.inventory.save(_inventory("inv-b", client_id=None))
    repos.aisle.save(_aisle("aisle-b", inventory_id="inv-b"))
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/aisles/aisle-b/assets",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == AISLE_NOT_FOUND
    assert counter.count == 1  # spool ran; the aisle-ownership check is post-spool defense-in-depth.
    assert storage.save_calls == 0
    assert list(repos.source_asset.list_by_aisle("aisle-b")) == []


def test_aisle_asset_upload_platform_actor_succeeds_after_auth_and_spool_runs(
    api_client: TestClient, repos: _Repos, monkeypatch
) -> None:
    """Positive control: a valid aisle for a platform actor passes auth and the route body runs."""
    counter = _wrap_async_call_counter(
        monkeypatch, assets_routes, "read_uploaded_files_for_aisle_asset_upload"
    )
    repos.inventory.save(_inventory("inv-a", client_id=None))
    repos.aisle.save(_aisle("aisle-a", inventory_id="inv-a"))
    stub_use_case = _StubUploadAisleAssetsUseCase()
    app.dependency_overrides[get_upload_aisle_assets_use_case] = lambda: stub_use_case
    _set_admin(_platform_admin())
    try:
        resp = api_client.post(
            "/api/v3/inventories/inv-a/aisles/aisle-a/assets",
            files=_ONE_FILE,
        )
    finally:
        _clear_admin()
        app.dependency_overrides.pop(get_upload_aisle_assets_use_case, None)

    assert resp.status_code == 201, resp.text
    assert counter.count == 1
    assert len(stub_use_case.calls) == 1
    _, kwargs = stub_use_case.calls[0]
    assert kwargs["principal"].is_platform is True
