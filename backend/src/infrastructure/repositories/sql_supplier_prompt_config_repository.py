"""SQL Server implementation of SupplierPromptConfigRepository — Phase D2."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import SupplierPromptConfigRepository
from src.database.sqlserver import SqlServerClient
from src.domain.client_supplier.prompt_config import SupplierPromptConfig


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_supplier_prompt_config(row) -> SupplierPromptConfig:
    created_at = _to_utc(getattr(row, "created_at", None))
    updated_at = _to_utc(getattr(row, "updated_at", None))
    if created_at is None:
        raise ValueError("supplier_prompt_configs row missing required created_at")
    if updated_at is None:
        raise ValueError("supplier_prompt_configs row missing required updated_at")
    return SupplierPromptConfig(
        id=getattr(row, "id", None),
        client_supplier_id=getattr(row, "client_supplier_id", None),
        provider_name=(getattr(row, "provider_name", None) or "").strip(),
        model_name=(getattr(row, "model_name", None) or "").strip() or None,
        instructions_text=getattr(row, "instructions_text", None),
        version=int(getattr(row, "version", 0)),
        is_active=bool(getattr(row, "is_active", False)),
        created_at=created_at,
        updated_at=updated_at,
    )


class SqlSupplierPromptConfigRepository(SupplierPromptConfigRepository):
    def __init__(self, client: SqlServerClient) -> None:
        self._client = client

    def create(self, config: SupplierPromptConfig) -> SupplierPromptConfig:
        created = _to_utc(config.created_at)
        updated = _to_utc(config.updated_at)
        if created is None:
            raise ValueError("SupplierPromptConfig.created_at is required")
        if updated is None:
            raise ValueError("SupplierPromptConfig.updated_at is required")
        with self._client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO supplier_prompt_configs (
                    id, client_supplier_id, provider_name, model_name, instructions_text,
                    version, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.id,
                    config.client_supplier_id,
                    config.provider_name.strip(),
                    (config.model_name or "").strip() or None,
                    config.instructions_text,
                    int(config.version),
                    1 if config.is_active else 0,
                    created,
                    updated,
                ),
            )
        return config

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierPromptConfig]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                ORDER BY provider_name ASC,
                         model_scope_key ASC,
                         version DESC,
                         created_at DESC,
                         id ASC
                """,
                (client_supplier_id,),
            )
            rows = cur.fetchall()
        return [_row_to_supplier_prompt_config(row) for row in rows]

    def list_versions_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> Sequence[SupplierPromptConfig]:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND provider_name = ?
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                (client_supplier_id, provider_name, model_name, model_name),
            )
            rows = cur.fetchall()
        return [_row_to_supplier_prompt_config(row) for row in rows]

    def get_by_id(self, config_id: str) -> SupplierPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            row = cur.fetchone()
        return _row_to_supplier_prompt_config(row) if row else None

    def get_active_by_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> SupplierPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND provider_name = ?
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                (client_supplier_id, provider_name, model_name, model_name),
            )
            row = cur.fetchone()
        return _row_to_supplier_prompt_config(row) if row else None

    def get_latest_version_number(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> int | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(version) AS max_version
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND provider_name = ?
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                """,
                (client_supplier_id, provider_name, model_name, model_name),
            )
            row = cur.fetchone()
        if not row or getattr(row, "max_version", None) is None:
            return None
        return int(row.max_version)

    def deactivate_scope(
        self,
        client_supplier_id: str,
        provider_name: str,
        model_name: str | None,
    ) -> None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                UPDATE supplier_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE client_supplier_id = ?
                  AND provider_name = ?
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                """,
                (client_supplier_id, provider_name, model_name, model_name),
            )

    def activate_version(self, config_id: str) -> SupplierPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            supplier_id = getattr(row, "client_supplier_id", None)
            provider_name = getattr(row, "provider_name", None)
            model_name = getattr(row, "model_name", None)

            cur.execute(
                """
                UPDATE supplier_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE client_supplier_id = ?
                  AND provider_name = ?
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                """,
                (supplier_id, provider_name, model_name, model_name),
            )
            cur.execute(
                """
                UPDATE supplier_prompt_configs
                SET is_active = 1,
                    updated_at = SYSUTCDATETIME()
                WHERE id = ?
                """,
                (config_id,),
            )
            cur.execute(
                """
                SELECT id, client_supplier_id, provider_name, model_name, instructions_text,
                       version, is_active, created_at, updated_at
                FROM supplier_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            updated_row = cur.fetchone()
        return _row_to_supplier_prompt_config(updated_row) if updated_row else None
