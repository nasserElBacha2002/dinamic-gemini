"""Parse and import Raspberry offline configuration packages."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config.inventory_catalog import (
    InventoryCatalogDocument,
    InventoryCatalogEntry,
    InventoryCatalogError,
    InventoryCatalogRepository,
    merge_catalog_documents,
)
from config.inventory_context_sync import operational_config_from_recognition_bundle
from config.models import (
    ClientRecognitionConfig,
    RecognitionSnapshot,
    SnapshotValidationError,
    SUPPORTED_SCHEMA_VERSION,
)
from config.repository import SnapshotRepository


OFFLINE_PACKAGE_SCHEMA_VERSION = 1
_PACKAGE_IMPORT_LOCK = threading.Lock()


class OfflinePackageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class OfflinePackage:
    package_schema_version: int
    generated_at: str
    recognition: RecognitionSnapshot
    catalog: InventoryCatalogDocument


@dataclass(frozen=True)
class OfflinePackageImportResult:
    clients_added: int
    clients_updated: int
    inventories_added: int
    inventories_updated: int
    contexts_added: int
    contexts_updated: int


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OfflinePackageError("PACKAGE_INVALID", f"{field} must be a non-empty string")
    return value.strip()


def parse_offline_package(data: Any) -> OfflinePackage:
    if not isinstance(data, dict):
        raise OfflinePackageError("PACKAGE_INVALID", "package must be a JSON object")
    version = data.get("package_schema_version")
    if version != OFFLINE_PACKAGE_SCHEMA_VERSION:
        raise OfflinePackageError(
            "PACKAGE_UNSUPPORTED_SCHEMA",
            f"unsupported package_schema_version: {version}",
        )
    generated_at = _required_string(data.get("generated_at"), "generated_at")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OfflinePackageError(
            "PACKAGE_INVALID",
            "generated_at must be ISO-8601",
        ) from exc
    recognition_raw = data.get("recognition")
    if not isinstance(recognition_raw, dict):
        raise OfflinePackageError("PACKAGE_INVALID", "recognition must be an object")
    try:
        recognition = RecognitionSnapshot.from_dict(recognition_raw)
    except SnapshotValidationError as exc:
        raise OfflinePackageError("PACKAGE_INVALID", str(exc)) from exc

    raw_inventories = data.get("inventories")
    if raw_inventories is None:
        raw_inventories = []
    if not isinstance(raw_inventories, list):
        raise OfflinePackageError("PACKAGE_INVALID", "inventories must be an array")

    inventories: list[InventoryCatalogEntry] = []
    for row in raw_inventories:
        try:
            inventories.append(InventoryCatalogEntry.from_dict(row))
        except InventoryCatalogError as exc:
            raise OfflinePackageError(exc.code, str(exc)) from exc

    raw_configs = data.get("inventory_recognition_configs")
    if raw_configs is None:
        raw_configs = []
    if not isinstance(raw_configs, list):
        raise OfflinePackageError(
            "PACKAGE_INVALID",
            "inventory_recognition_configs must be an array",
        )

    catalog_entries: dict[str, InventoryCatalogEntry] = {
        entry.inventory_id: entry for entry in inventories
    }
    contexts: dict[str, Any] = {}
    for row in raw_configs:
        if not isinstance(row, dict):
            raise OfflinePackageError(
                "PACKAGE_INVALID",
                "inventory_recognition_configs entries must be objects",
            )
        try:
            operational = operational_config_from_recognition_bundle(row)
        except Exception as exc:
            raise OfflinePackageError(
                "PACKAGE_INVALID",
                f"invalid inventory recognition config: {exc}",
            ) from exc
        contexts[operational.inventory_id] = operational
        if operational.inventory_id not in catalog_entries:
            client_id = str(row.get("client_id") or operational.client_id or "").strip()
            if not client_id:
                raise OfflinePackageError(
                    "PACKAGE_INVALID",
                    f"inventory {operational.inventory_id} missing client_id",
                )
            catalog_entries[operational.inventory_id] = InventoryCatalogEntry(
                inventory_id=operational.inventory_id,
                name=operational.inventory_id,
                client_id=client_id,
                status="imported",
            )

    incoming_catalog = InventoryCatalogDocument(
        catalog_schema_version=1,
        inventories=catalog_entries,
        contexts=contexts,
    )

    return OfflinePackage(
        package_schema_version=OFFLINE_PACKAGE_SCHEMA_VERSION,
        generated_at=generated_at,
        recognition=recognition,
        catalog=incoming_catalog,
    )


def merge_recognition_snapshots(
    base: RecognitionSnapshot | None,
    incoming: RecognitionSnapshot,
) -> tuple[RecognitionSnapshot, int, int]:
    existing = {client.client_id: client for client in (base.clients if base else ())}
    added = 0
    updated = 0
    for client in incoming.clients:
        if client.client_id in existing:
            updated += 1
        else:
            added += 1
        existing[client.client_id] = client
    clients = tuple(sorted(existing.values(), key=lambda row: row.client_id))
    merged = RecognitionSnapshot(
        bundle_schema_version=SUPPORTED_SCHEMA_VERSION,
        generated_at=incoming.generated_at,
        bundle_revision=_merged_bundle_revision(clients),
        clients=clients,
    )
    return merged, added, updated


def _merged_bundle_revision(
    clients: tuple[ClientRecognitionConfig, ...],
) -> str:
    payload = {
        "bundle_schema_version": SUPPORTED_SCHEMA_VERSION,
        "clients": [
            {
                "client_id": client.client_id,
                "name": client.name,
                "bundle_revision": client.bundle_revision,
            }
            for client in clients
        ],
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_replace_pair(
    *,
    snapshot_repository: SnapshotRepository,
    catalog_repository: InventoryCatalogRepository,
    merged_snapshot: RecognitionSnapshot,
    merged_catalog: InventoryCatalogDocument,
) -> None:
    snapshot_path = snapshot_repository.path
    catalog_path = catalog_repository.path
    parent = snapshot_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging_dir = parent / f".offline-import-{os.getpid()}-{threading.get_ident()}"
    staging_dir.mkdir()
    snap_stage = staging_dir / snapshot_path.name
    cat_stage = staging_dir / catalog_path.name
    snap_backup = staging_dir / f"{snapshot_path.name}.bak"
    cat_backup = staging_dir / f"{catalog_path.name}.bak"
    snapshot_replaced = False
    try:
        SnapshotRepository(snap_stage).save(merged_snapshot)
        InventoryCatalogRepository(cat_stage).save(merged_catalog)
        if snapshot_path.exists():
            shutil.copy2(snapshot_path, snap_backup)
        if catalog_path.exists():
            shutil.copy2(catalog_path, cat_backup)
        os.replace(snap_stage, snapshot_path)
        snapshot_replaced = True
        try:
            os.replace(cat_stage, catalog_path)
        except OSError:
            if snap_backup.exists():
                os.replace(snap_backup, snapshot_path)
            elif snapshot_replaced:
                snapshot_path.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


class OfflinePackageImporter:
    def __init__(
        self,
        snapshot_repository: SnapshotRepository,
        catalog_repository: InventoryCatalogRepository,
    ) -> None:
        self._snapshot_repository = snapshot_repository
        self._catalog_repository = catalog_repository

    def import_json_bytes(self, raw: bytes) -> OfflinePackageImportResult:
        with _PACKAGE_IMPORT_LOCK:
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OfflinePackageError("PACKAGE_INVALID", "file is not valid JSON") from exc

            package = parse_offline_package(data)

            current_snapshot = self._snapshot_repository.load()
            merged_snapshot, clients_added, clients_updated = merge_recognition_snapshots(
                current_snapshot,
                package.recognition,
            )

            current_catalog = self._catalog_repository.load()
            incoming_catalog = package.catalog
            merged_catalog, catalog_stats = merge_catalog_documents(
                current_catalog,
                incoming_catalog,
            )

            _atomic_replace_pair(
                snapshot_repository=self._snapshot_repository,
                catalog_repository=self._catalog_repository,
                merged_snapshot=merged_snapshot,
                merged_catalog=merged_catalog,
            )

            return OfflinePackageImportResult(
                clients_added=clients_added,
                clients_updated=clients_updated,
                inventories_added=catalog_stats["inventories_added"],
                inventories_updated=catalog_stats["inventories_updated"],
                contexts_added=catalog_stats["contexts_added"],
                contexts_updated=catalog_stats["contexts_updated"],
            )
