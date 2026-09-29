"""Thread-safe snapshot lifecycle: load LKG, synchronize, and expose offline config."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .models import RecognitionSnapshot
from .repository import SnapshotRepository
from .sync import BackendSnapshotClient


class ConfigService:
    def __init__(
        self,
        repository: SnapshotRepository,
        backend_client: BackendSnapshotClient | None,
        client_id: str | None,
    ) -> None:
        self._repository = repository
        self._backend_client = backend_client
        self._client_id = client_id.strip() if client_id else None
        self._lock = threading.Lock()
        self._sync_lock = threading.Lock()
        self._snapshot: RecognitionSnapshot | None = None
        self._load_error: str | None = None
        self._last_sync_attempt_at: str | None = None
        self._last_sync_success_at: str | None = None
        self._last_sync_error: str | None = None
        try:
            loaded = repository.load()
            if loaded is not None and self._client_id and loaded.client_id != self._client_id:
                raise ValueError(
                    f"persisted snapshot belongs to client {loaded.client_id}, expected {self._client_id}"
                )
            self._snapshot = loaded
        except Exception as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"

    def sync(self) -> dict[str, Any]:
        attempted_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._last_sync_attempt_at = attempted_at
        if self._backend_client is None or not self._client_id:
            with self._lock:
                self._last_sync_error = "backend sync is not configured"
                return self._status_locked()
        if not self._sync_lock.acquire(blocking=False):
            with self._lock:
                return self._status_locked()
        try:
            try:
                candidate = self._backend_client.fetch(self._client_id)
                if candidate.client_id != self._client_id:
                    raise ValueError(
                        f"backend snapshot belongs to client {candidate.client_id}, expected {self._client_id}"
                    )
                with self._lock:
                    current = self._snapshot
                if current is None or current.bundle_revision != candidate.bundle_revision:
                    self._repository.save(candidate)
                    with self._lock:
                        self._snapshot = candidate
                with self._lock:
                    self._last_sync_success_at = datetime.now(timezone.utc).isoformat()
                    self._last_sync_error = None
                    self._load_error = None
                    return self._status_locked()
            except Exception as exc:
                with self._lock:
                    self._last_sync_error = f"{type(exc).__name__}: {exc}"
                    return self._status_locked()
        finally:
            self._sync_lock.release()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def snapshot(self) -> RecognitionSnapshot | None:
        with self._lock:
            return self._snapshot

    def suppliers(self) -> list[dict[str, str]]:
        with self._lock:
            if self._snapshot is None:
                return []
            return [supplier.as_dict() for supplier in self._snapshot.suppliers]

    def supplier_config(self, supplier_id: str) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None:
                return None
            supplier = snapshot.supplier(supplier_id)
            if supplier is None:
                return None
            return {
                **supplier.as_dict(),
                "item_profile": (
                    snapshot.profile(supplier_id, "ITEM").as_dict()
                    if supplier.item_source == "SUPPLIER" and snapshot.profile(supplier_id, "ITEM")
                    else None
                ),
                "position_profile": (
                    snapshot.profile(supplier_id, "POSITION").as_dict()
                    if supplier.position_source == "SUPPLIER" and snapshot.profile(supplier_id, "POSITION")
                    else None
                ),
            }

    def _status_locked(self) -> dict[str, Any]:
        snapshot = self._snapshot

        if snapshot is None:
            config_state = "UNAVAILABLE"
        elif self._last_sync_error is not None:
            config_state = "OFFLINE_READY"
        else:
            config_state = "READY"

        return {
            "config_state": config_state,
            "configured_client_id": self._client_id,
            "available_offline": snapshot is not None,
            "client_id": snapshot.client_id if snapshot else None,
            "bundle_schema_version": snapshot.bundle_schema_version if snapshot else None,
            "bundle_revision": snapshot.bundle_revision if snapshot else None,
            "generated_at": snapshot.generated_at if snapshot else None,
            "supplier_count": len(snapshot.suppliers) if snapshot else 0,
            "profile_count": len(snapshot.profiles) if snapshot else 0,
            "sync_running": self._sync_lock.locked(),
            "last_sync_attempt_at": self._last_sync_attempt_at,
            "last_sync_success_at": self._last_sync_success_at,
            "last_sync_error": self._last_sync_error,
            "load_error": self._load_error,
            "storage_path": str(self._repository.path),
        }