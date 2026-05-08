"""In-memory implementation of GlobalPromptConfigRepository — Phase D9."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import GlobalPromptConfigRepository
from src.domain.global_prompt_config import GlobalPromptConfig

DEFAULT_MODEL_SCOPE_KEY = "#NULL#"
MODEL_SCOPE_PREFIX = "M:"


def _scope_key(
    scope_type: str,
    provider_name: str | None,
    model_name: str | None,
) -> tuple[str, str | None, str]:
    normalized_scope = (scope_type or "").strip().lower() or "global"
    normalized_provider = (provider_name or "").strip().lower() or None
    normalized_model = (model_name or "").strip() or None
    model_scope_key = (
        DEFAULT_MODEL_SCOPE_KEY
        if normalized_model is None
        else f"{MODEL_SCOPE_PREFIX}{normalized_model}"
    )
    return (normalized_scope, normalized_provider, model_scope_key)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_config(config: GlobalPromptConfig) -> GlobalPromptConfig:
    return GlobalPromptConfig(
        id=config.id,
        scope_type="global",
        provider_name=(config.provider_name or "").strip().lower() or None,
        model_name=(config.model_name or "").strip() or None,
        instructions_text=config.instructions_text,
        version=config.version,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


class MemoryGlobalPromptConfigRepository(GlobalPromptConfigRepository):
    def __init__(self) -> None:
        self._store: dict[str, GlobalPromptConfig] = {}

    def create(self, config: GlobalPromptConfig) -> GlobalPromptConfig:
        normalized = _normalize_config(config)
        if normalized.id in self._store:
            raise ValueError(f"GlobalPromptConfig with id={normalized.id!r} already exists")
        sk = _scope_key(normalized.scope_type, normalized.provider_name, normalized.model_name)
        if any(
            _scope_key(row.scope_type, row.provider_name, row.model_name) == sk
            and row.version == normalized.version
            for row in self._store.values()
        ):
            raise ValueError("GlobalPromptConfig version already exists in scope")
        if normalized.is_active and any(
            _scope_key(row.scope_type, row.provider_name, row.model_name) == sk
            and row.is_active
            for row in self._store.values()
        ):
            raise ValueError("Only one active GlobalPromptConfig is allowed per scope")
        self._store[normalized.id] = normalized
        return normalized

    def list_versions(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> Sequence[GlobalPromptConfig]:
        sk = _scope_key(scope_type, provider_name, model_name)
        rows = [
            row
            for row in self._store.values()
            if _scope_key(row.scope_type, row.provider_name, row.model_name) == sk
        ]
        rows.sort(
            key=lambda row: (-int(row.version), -_ensure_utc(row.created_at).timestamp(), row.id)
        )
        return rows

    def get_by_id(self, config_id: str) -> GlobalPromptConfig | None:
        return self._store.get(config_id)

    def get_active(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> GlobalPromptConfig | None:
        sk = _scope_key(scope_type, provider_name, model_name)
        rows = [
            row
            for row in self._store.values()
            if _scope_key(row.scope_type, row.provider_name, row.model_name) == sk
            and row.is_active
        ]
        rows.sort(
            key=lambda row: (-int(row.version), -_ensure_utc(row.created_at).timestamp(), row.id)
        )
        return rows[0] if rows else None

    def get_latest_version_number(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> int | None:
        sk = _scope_key(scope_type, provider_name, model_name)
        versions = [
            int(row.version)
            for row in self._store.values()
            if _scope_key(row.scope_type, row.provider_name, row.model_name) == sk
        ]
        return max(versions) if versions else None

    def deactivate_scope(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        sk = _scope_key(scope_type, provider_name, model_name)
        now = datetime.now(timezone.utc)
        for row in list(self._store.values()):
            if _scope_key(row.scope_type, row.provider_name, row.model_name) == sk and row.is_active:
                self._store[row.id] = GlobalPromptConfig(
                    id=row.id,
                    scope_type=row.scope_type,
                    provider_name=row.provider_name,
                    model_name=row.model_name,
                    instructions_text=row.instructions_text,
                    version=row.version,
                    is_active=False,
                    created_at=row.created_at,
                    updated_at=now,
                )

    def activate_version(self, config_id: str) -> GlobalPromptConfig | None:
        row = self._store.get(config_id)
        if row is None:
            return None
        sk = _scope_key(row.scope_type, row.provider_name, row.model_name)
        now = datetime.now(timezone.utc)
        for existing in list(self._store.values()):
            if _scope_key(existing.scope_type, existing.provider_name, existing.model_name) == sk:
                self._store[existing.id] = GlobalPromptConfig(
                    id=existing.id,
                    scope_type=existing.scope_type,
                    provider_name=existing.provider_name,
                    model_name=existing.model_name,
                    instructions_text=existing.instructions_text,
                    version=existing.version,
                    is_active=(existing.id == config_id),
                    created_at=existing.created_at,
                    updated_at=now
                    if existing.id == config_id or existing.is_active
                    else existing.updated_at,
                )
        return self._store[config_id]
