"""Thread-safe global snapshot lifecycle and offline recognition queries."""

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
    ) -> None:
        self._repository = repository
        self._backend_client = backend_client

        self._lock = threading.Lock()
        self._sync_lock = threading.Lock()

        self._snapshot: RecognitionSnapshot | None = None
        self._load_error: str | None = None
        self._last_sync_attempt_at: str | None = None
        self._last_sync_success_at: str | None = None
        self._last_sync_error: str | None = None

        try:
            self._snapshot = repository.load()
        except Exception as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"

    def sync(self) -> dict[str, Any]:
        attempted_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._last_sync_attempt_at = attempted_at

        if self._backend_client is None:
            with self._lock:
                self._last_sync_error = "backend sync is not configured"
                return self._status_locked()

        if not self._sync_lock.acquire(blocking=False):
            with self._lock:
                return self._status_locked()

        try:
            try:
                candidate = self._backend_client.fetch()

                with self._lock:
                    current = self._snapshot

                if (
                    current is None
                    or current.bundle_revision
                    != candidate.bundle_revision
                ):
                    self._repository.save(candidate)

                    with self._lock:
                        self._snapshot = candidate

                with self._lock:
                    self._last_sync_success_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    self._last_sync_error = None
                    self._load_error = None
                    return self._status_locked()

            except Exception as exc:
                with self._lock:
                    self._last_sync_error = (
                        f"{type(exc).__name__}: {exc}"
                    )
                    return self._status_locked()

        finally:
            self._sync_lock.release()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked()

    def snapshot(self) -> RecognitionSnapshot | None:
        with self._lock:
            return self._snapshot

    def clients(self) -> list[dict[str, str]]:
        with self._lock:
            snapshot = self._snapshot

            if snapshot is None:
                return []

            return [
                {
                    "client_id": client.client_id,
                    "name": client.name,
                    "bundle_revision": client.bundle_revision,
                }
                for client in snapshot.clients
            ]

    def client_config(
        self,
        client_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._snapshot

            if snapshot is None:
                return None

            client = snapshot.client(client_id)

            if client is None:
                return None

            return client.as_dict()

    def suppliers(
        self,
        client_id: str,
    ) -> list[dict[str, str]]:
        with self._lock:
            snapshot = self._snapshot

            if snapshot is None:
                return []

            client = snapshot.client(client_id)

            if client is None:
                return []

            return [
                supplier.as_dict()
                for supplier in client.suppliers
            ]

    def supplier_config(
        self,
        client_id: str,
        supplier_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            snapshot = self._snapshot

            if snapshot is None:
                return None

            client = snapshot.client(client_id)

            if client is None:
                return None

            supplier = client.supplier(supplier_id)

            if supplier is None:
                return None

            item_profile = client.profile(
                supplier_id,
                "ITEM",
            )
            position_profile = client.profile(
                supplier_id,
                "POSITION",
            )

            return {
                **supplier.as_dict(),
                "item_profile": (
                    item_profile.as_dict()
                    if supplier.item_source == "SUPPLIER"
                    and item_profile is not None
                    else None
                ),
                "position_profile": (
                    position_profile.as_dict()
                    if supplier.position_source == "SUPPLIER"
                    and position_profile is not None
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

        client_count = 0
        supplier_count = 0
        profile_count = 0

        if snapshot is not None:
            client_count = len(snapshot.clients)
            supplier_count = sum(
                len(client.suppliers)
                for client in snapshot.clients
            )
            profile_count = sum(
                len(client.profiles)
                for client in snapshot.clients
            )

        return {
            "config_state": config_state,
            "available_offline": snapshot is not None,
            "bundle_schema_version": (
                snapshot.bundle_schema_version
                if snapshot
                else None
            ),
            "bundle_revision": (
                snapshot.bundle_revision
                if snapshot
                else None
            ),
            "generated_at": (
                snapshot.generated_at
                if snapshot
                else None
            ),
            "client_count": client_count,
            "supplier_count": supplier_count,
            "profile_count": profile_count,
            "sync_running": self._sync_lock.locked(),
            "last_sync_attempt_at": self._last_sync_attempt_at,
            "last_sync_success_at": self._last_sync_success_at,
            "last_sync_error": self._last_sync_error,
            "load_error": self._load_error,
            "storage_path": str(self._repository.path),
        }