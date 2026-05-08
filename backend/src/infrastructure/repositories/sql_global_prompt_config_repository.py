"""SQL Server implementation of GlobalPromptConfigRepository — Phase D9."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import GlobalPromptConfigRepository
from src.database.sqlserver import SqlServerClient
from src.domain.global_prompt_config import GlobalPromptConfig


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_global_prompt_config(row) -> GlobalPromptConfig:
    created_at = _to_utc(getattr(row, "created_at", None))
    updated_at = _to_utc(getattr(row, "updated_at", None))
    if created_at is None:
        raise ValueError("global_prompt_configs row missing required created_at")
    if updated_at is None:
        raise ValueError("global_prompt_configs row missing required updated_at")
    return GlobalPromptConfig(
        id=getattr(row, "id", None),
        scope_type=(getattr(row, "scope_type", None) or "").strip().lower() or "global",
        provider_name=(getattr(row, "provider_name", None) or "").strip().lower() or None,
        model_name=(getattr(row, "model_name", None) or "").strip() or None,
        instructions_text=getattr(row, "instructions_text", None),
        version=int(getattr(row, "version", 0)),
        is_active=bool(getattr(row, "is_active", False)),
        created_at=created_at,
        updated_at=updated_at,
    )


class SqlGlobalPromptConfigRepository(GlobalPromptConfigRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create(self, config: GlobalPromptConfig) -> GlobalPromptConfig:
        created = _to_utc(config.created_at)
        updated = _to_utc(config.updated_at)
        if created is None:
            raise ValueError("GlobalPromptConfig.created_at is required")
        if updated is None:
            raise ValueError("GlobalPromptConfig.updated_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO global_prompt_configs (
                    id, scope_type, provider_name, model_name, instructions_text,
                    version, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.id,
                    "global",
                    (config.provider_name or "").strip().lower() or None,
                    (config.model_name or "").strip() or None,
                    config.instructions_text,
                    int(config.version),
                    1 if config.is_active else 0,
                    created,
                    updated,
                ),
            )
        return config

    def list_versions(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> Sequence[GlobalPromptConfig]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, scope_type, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM global_prompt_configs
                WHERE scope_type = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                (scope_type.strip().lower(), provider_name, provider_name, model_name, model_name),
            )
            rows = cur.fetchall()
        return [_row_to_global_prompt_config(row) for row in rows]

    def get_by_id(self, config_id: str) -> GlobalPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, scope_type, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM global_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            row = cur.fetchone()
        return _row_to_global_prompt_config(row) if row else None

    def get_active(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> GlobalPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, scope_type, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM global_prompt_configs
                WHERE scope_type = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                (scope_type.strip().lower(), provider_name, provider_name, model_name, model_name),
            )
            row = cur.fetchone()
        return _row_to_global_prompt_config(row) if row else None

    def get_latest_version_number(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> int | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(version) AS max_version
                FROM global_prompt_configs
                WHERE scope_type = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                """,
                (scope_type.strip().lower(), provider_name, provider_name, model_name, model_name),
            )
            row = cur.fetchone()
        if not row or getattr(row, "max_version", None) is None:
            return None
        return int(row.max_version)

    def deactivate_scope(
        self,
        scope_type: str = "global",
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE global_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE scope_type = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                """,
                (scope_type.strip().lower(), provider_name, provider_name, model_name, model_name),
            )

    def activate_version(self, config_id: str) -> GlobalPromptConfig | None:
        # Atomic by project convention: SqlServerClient.cursor commits once on success
        # and rolls back the full block on any exception.
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, scope_type, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM global_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            scope_type = getattr(row, "scope_type", None)
            provider_name = getattr(row, "provider_name", None)
            model_name = getattr(row, "model_name", None)

            cur.execute(
                """
                UPDATE global_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE scope_type = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                """,
                (scope_type, provider_name, provider_name, model_name, model_name),
            )
            cur.execute(
                """
                UPDATE global_prompt_configs
                SET is_active = 1,
                    updated_at = SYSUTCDATETIME()
                WHERE id = ?
                """,
                (config_id,),
            )
            cur.execute(
                """
                SELECT id, scope_type, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM global_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            updated_row = cur.fetchone()
        return _row_to_global_prompt_config(updated_row) if updated_row else None
