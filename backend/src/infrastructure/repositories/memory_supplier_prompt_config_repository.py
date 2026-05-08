"""In-memory implementation of SupplierPromptConfigRepository — Phase D2."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import SupplierPromptConfigRepository
from src.domain.client_supplier.prompt_config import SupplierPromptConfig

DEFAULT_MODEL_SCOPE_KEY = "#NULL#"
MODEL_SCOPE_PREFIX = "M:"


def _scope_key(
    client_supplier_id: str,
    provider_name: str,
    model_name: str | None,
) -> tuple[str, str, str]:
    normalized_model = (model_name or "").strip()
    model_scope_key = (
        DEFAULT_MODEL_SCOPE_KEY
        if not normalized_model
        else f"{MODEL_SCOPE_PREFIX}{normalized_model}"
    )
    return (client_supplier_id.strip(), provider_name.strip(), model_scope_key)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_config(config: SupplierPromptConfig) -> SupplierPromptConfig:
    return SupplierPromptConfig(
        id=config.id,
        client_supplier_id=config.client_supplier_id,
        provider_name=config.provider_name.strip(),
        model_name=(config.model_name or "").strip() or None,
        instructions_text=config.instructions_text,
        version=config.version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


class MemorySupplierPromptConfigRepository(SupplierPromptConfigRepository):
    def __init__(self) -> None:
        self._store: dict[str, SupplierPromptConfig] = {}

    def create(self, config: SupplierPromptConfig) -> SupplierPromptConfig:
        normalized = _normalize_config(config)
        if normalized.id in self._store:
            raise ValueError(f"SupplierPromptConfig with id={normalized.id!r} already exists")
        sk = _scope_key(
            normalized.client_supplier_id,
            normalized.provider_name,
            normalized.model_name,
        )
        if any(
            _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk
            and row.version == normalized.version
            for row in self._store.values()
        ):
            raise ValueError("SupplierPromptConfig version already exists in scope")
        if normalized.is_active and any(
            _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk
            and row.is_active
            for row in self._store.values()
        ):
            raise ValueError("Only one active SupplierPromptConfig is allowed per scope")
        self._store[normalized.id] = normalized
        return normalized

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierPromptConfig]:
        rows = [
            row
            for row in self._store.values()
            if row.client_supplier_id == client_supplier_id
        ]
        rows.sort(
            key=lambda row: (
                row.provider_name,
                _scope_key(row.client_supplier_id, row.provider_name, row.model_name)[2],
                -int(row.version),
                -_ensure_utc(row.created_at).timestamp(),
                row.id,
            )
        )
        return rows

    def list_versions_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> Sequence[SupplierPromptConfig]:
        sk = _scope_key(client_supplier_id, provider_name, model_name)
        rows = [
            row
            for row in self._store.values()
            if _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk
        ]
        rows.sort(
            key=lambda row: (-int(row.version), -_ensure_utc(row.created_at).timestamp(), row.id)
        )
        return rows

    def get_by_id(self, config_id: str) -> SupplierPromptConfig | None:
        return self._store.get(config_id)

    def get_active_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> SupplierPromptConfig | None:
        sk = _scope_key(client_supplier_id, provider_name, model_name)
        rows = [
            row
            for row in self._store.values()
            if _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk
            and row.is_active
        ]
        rows.sort(
            key=lambda row: (-int(row.version), -_ensure_utc(row.created_at).timestamp(), row.id)
        )
        return rows[0] if rows else None

    def get_latest_version_number(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> int | None:
        sk = _scope_key(client_supplier_id, provider_name, model_name)
        versions = [
            int(row.version)
            for row in self._store.values()
            if _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk
        ]
        return max(versions) if versions else None

    def deactivate_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> None:
        sk = _scope_key(client_supplier_id, provider_name, model_name)
        now = datetime.now(timezone.utc)
        for row in list(self._store.values()):
            if _scope_key(row.client_supplier_id, row.provider_name, row.model_name) == sk and row.is_active:
                self._store[row.id] = SupplierPromptConfig(
                    id=row.id,
                    client_supplier_id=row.client_supplier_id,
                    provider_name=row.provider_name,
                    model_name=row.model_name,
                    instructions_text=row.instructions_text,
                    version=row.version,
                    is_active=False,
                    created_at=row.created_at,
                    updated_at=now,
                )

    def activate_version(self, config_id: str) -> SupplierPromptConfig | None:
        row = self._store.get(config_id)
        if row is None:
            return None
        sk = _scope_key(row.client_supplier_id, row.provider_name, row.model_name)
        now = datetime.now(timezone.utc)
        for existing in list(self._store.values()):
            if _scope_key(existing.client_supplier_id, existing.provider_name, existing.model_name) == sk:
                self._store[existing.id] = SupplierPromptConfig(
                    id=existing.id,
                    client_supplier_id=existing.client_supplier_id,
                    provider_name=existing.provider_name,
                    model_name=existing.model_name,
                    instructions_text=existing.instructions_text,
                    version=existing.version,
                    is_active=(existing.id == config_id),
                    created_at=existing.created_at,
                    updated_at=now if existing.id == config_id or existing.is_active else existing.updated_at,
                )
        return self._store[config_id]
