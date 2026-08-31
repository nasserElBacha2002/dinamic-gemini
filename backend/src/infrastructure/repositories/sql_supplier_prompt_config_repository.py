"""SQL Server implementation of SupplierPromptConfigRepository — Phase D2."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from src.application.ports.repositories import SupplierPromptConfigRepository
from src.database.sqlserver import SqlServerClient
from src.domain.client_supplier.prompt_config import SupplierPromptConfig
from src.domain.label_profiles.kinds import LabelKind, effective_label_kind, parse_label_kind


def _to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _require_str(row: object, column: str) -> str:
    """Map a required DB column to a non-empty str; never coerce None into \"None\"."""
    raw = getattr(row, column, None)
    if raw is None:
        raise ValueError(f"supplier_prompt_configs row missing required column {column!r}")
    if isinstance(raw, str):
        value = raw.strip()
    else:
        value = str(raw).strip()
    if not value:
        raise ValueError(f"supplier_prompt_configs row has empty {column!r}")
    return value


_SELECT_PROMPT_COLUMNS = """
    id, client_supplier_id, provider_name, model_name, instructions_text,
    version, is_active, created_at, updated_at, label_kind
"""


def _label_kind_scope_value(kind: LabelKind | None) -> str:
    return effective_label_kind(kind).value


def _row_to_supplier_prompt_config(row: object) -> SupplierPromptConfig:
    created_at = _to_utc(getattr(row, "created_at", None))
    updated_at = _to_utc(getattr(row, "updated_at", None))
    if created_at is None:
        raise ValueError("supplier_prompt_configs row missing required created_at")
    if updated_at is None:
        raise ValueError("supplier_prompt_configs row missing required updated_at")
    label_kind_raw = getattr(row, "label_kind", None)
    label_kind = parse_label_kind(str(label_kind_raw)) if label_kind_raw else None
    return SupplierPromptConfig(
        id=_require_str(row, "id"),
        client_supplier_id=_require_str(row, "client_supplier_id"),
        provider_name=(getattr(row, "provider_name", None) or "").strip() or None,
        model_name=(getattr(row, "model_name", None) or "").strip() or None,
        instructions_text=_require_str(row, "instructions_text"),
        version=int(getattr(row, "version", 0)),
        is_active=bool(getattr(row, "is_active", False)),
        created_at=created_at,
        updated_at=updated_at,
        label_kind=label_kind,
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
                    version, is_active, created_at, updated_at, label_kind
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config.id,
                    config.client_supplier_id,
                    (config.provider_name or "").strip() or None,
                    (config.model_name or "").strip() or None,
                    config.instructions_text,
                    int(config.version),
                    1 if config.is_active else 0,
                    created,
                    updated,
                    _label_kind_scope_value(config.label_kind),
                ),
            )
        return config

    def list_by_supplier(self, client_supplier_id: str) -> Sequence[SupplierPromptConfig]:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                ORDER BY provider_scope_key ASC,
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
        provider_name: str | None,
        model_name: str | None,
        label_kind: LabelKind | None = None,
    ) -> Sequence[SupplierPromptConfig]:
        kind_filter = ""
        params: list[object] = [client_supplier_id, provider_name, provider_name, model_name, model_name]
        if label_kind is not None:
            kind_filter = " AND ISNULL(label_kind, 'ITEM') = ?"
            params.append(_label_kind_scope_value(label_kind))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  {kind_filter}
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        return [_row_to_supplier_prompt_config(row) for row in rows]

    def get_by_id(self, config_id: str) -> SupplierPromptConfig | None:
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
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
        provider_name: str | None,
        model_name: str | None,
        label_kind: LabelKind | None = None,
    ) -> SupplierPromptConfig | None:
        kind_filter = ""
        params: list[object] = [client_supplier_id, provider_name, provider_name, model_name, model_name]
        if label_kind is not None:
            kind_filter = " AND ISNULL(label_kind, 'ITEM') = ?"
            params.append(_label_kind_scope_value(label_kind))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                  {kind_filter}
                ORDER BY version DESC, created_at DESC, id ASC
                """,
                tuple(params),
            )
            row = cur.fetchone()
        return _row_to_supplier_prompt_config(row) if row else None

    def get_latest_version_number(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
        label_kind: LabelKind | None = None,
    ) -> int | None:
        kind_filter = ""
        params: list[object] = [client_supplier_id, provider_name, provider_name, model_name, model_name]
        if label_kind is not None:
            kind_filter = " AND ISNULL(label_kind, 'ITEM') = ?"
            params.append(_label_kind_scope_value(label_kind))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(version) AS max_version
                FROM supplier_prompt_configs
                WHERE client_supplier_id = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  {kind_filter}
                """,
                tuple(params),
            )
            row = cur.fetchone()
        if not row or getattr(row, "max_version", None) is None:
            return None
        return int(row.max_version)

    def deactivate_scope(
        self,
        client_supplier_id: str,
        provider_name: str | None,
        model_name: str | None,
        label_kind: LabelKind | None = None,
    ) -> None:
        kind_filter = ""
        params: list[object] = [client_supplier_id, provider_name, provider_name, model_name, model_name]
        if label_kind is not None:
            kind_filter = " AND ISNULL(label_kind, 'ITEM') = ?"
            params.append(_label_kind_scope_value(label_kind))
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                UPDATE supplier_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE client_supplier_id = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND is_active = 1
                  {kind_filter}
                """,
                tuple(params),
            )

    def activate_version(self, config_id: str) -> SupplierPromptConfig | None:
        # Atomic by project convention: SqlServerClient.cursor commits once on success
        # and rolls back the full block on any exception.
        with self._client.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
                FROM supplier_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            supplier_id = row.client_supplier_id
            provider_name = row.provider_name
            model_name = row.model_name
            kind_value = _label_kind_scope_value(
                parse_label_kind(str(row.label_kind)) if getattr(row, "label_kind", None) else None
            )

            cur.execute(
                """
                UPDATE supplier_prompt_configs
                SET is_active = 0,
                    updated_at = SYSUTCDATETIME()
                WHERE client_supplier_id = ?
                  AND ((? IS NULL AND provider_name IS NULL) OR provider_name = ?)
                  AND ((? IS NULL AND model_name IS NULL) OR model_name = ?)
                  AND ISNULL(label_kind, 'ITEM') = ?
                  AND is_active = 1
                """,
                (supplier_id, provider_name, provider_name, model_name, model_name, kind_value),
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
                f"""
                SELECT {_SELECT_PROMPT_COLUMNS}
                FROM supplier_prompt_configs
                WHERE id = ?
                """,
                (config_id,),
            )
            updated_row = cur.fetchone()
        return _row_to_supplier_prompt_config(updated_row) if updated_row else None
