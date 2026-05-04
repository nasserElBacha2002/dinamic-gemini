"""Generic SQL Server migration lifecycle and schema compatibility guard."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from src.database.sqlserver import SqlServerClient, now_utc

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "versions"
_MIGRATION_TABLE = "schema_migrations"


class SchemaCompatibilityError(RuntimeError):
    """Raised when app code and DB schema are incompatible."""


@dataclass(frozen=True)
class MigrationFile:
    version: str
    name: str
    path: Path
    checksum_sha256: str


@dataclass(frozen=True)
class SchemaCompatibilityStatus:
    service: str
    required_version: str
    current_version: str | None
    compatible: bool
    last_applied_migration: str | None
    reason: str | None = None


@dataclass(frozen=True)
class MigrationStatus:
    service: str
    required_version: str
    current_version: str | None
    pending_versions: list[str]
    compatible: bool
    last_applied_migration: str | None


def _split_sql_batches(sql_text: str) -> list[str]:
    batches: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        if line.strip().upper() == "GO":
            chunk = "\n".join(current).strip()
            if chunk:
                batches.append(chunk)
            current = []
            continue
        current.append(line)
    tail = "\n".join(current).strip()
    if tail:
        batches.append(tail)
    return batches


def _list_migration_files() -> list[MigrationFile]:
    if not _MIGRATIONS_DIR.exists():
        return []
    migration_files: list[MigrationFile] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        stem = path.stem
        if "_" not in stem:
            continue
        version, name = stem.split("_", 1)
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        migration_files.append(
            MigrationFile(version=version, name=name, path=path, checksum_sha256=checksum)
        )
    return migration_files


def _ensure_migration_table(client: SqlServerClient) -> None:
    with client.cursor() as cur:
        cur.execute(
            f"""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{_MIGRATION_TABLE}')
            BEGIN
                CREATE TABLE {_MIGRATION_TABLE} (
                    id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    service_name VARCHAR(128) NOT NULL,
                    version VARCHAR(64) NOT NULL,
                    migration_name NVARCHAR(255) NOT NULL,
                    checksum_sha256 VARCHAR(64) NOT NULL,
                    deployment_id VARCHAR(128) NULL,
                    applied_at DATETIME2 NOT NULL,
                    UNIQUE (service_name, version)
                );
                CREATE INDEX IX_schema_migrations_service_version
                    ON {_MIGRATION_TABLE}(service_name, version);
                CREATE INDEX IX_schema_migrations_service_applied
                    ON {_MIGRATION_TABLE}(service_name, applied_at DESC);
            END
            """
        )


def _acquire_migration_lock(client: SqlServerClient, service: str, timeout_ms: int) -> None:
    with client.cursor() as cur:
        cur.execute(
            """
            DECLARE @result INT;
            EXEC @result = sp_getapplock
                @Resource = ?,
                @LockMode = 'Exclusive',
                @LockOwner = 'Session',
                @LockTimeout = ?;
            SELECT @result AS lock_result;
            """,
            (f"schema-migration:{service}", timeout_ms),
        )
        row = cur.fetchone()
        code = int(getattr(row, "lock_result", row[0] if row else -999))
        if code < 0:
            raise RuntimeError(
                f"Failed to acquire migration lock for service={service}, code={code}"
            )


def _fetch_applied_versions(client: SqlServerClient, service: str) -> list[str]:
    with client.cursor() as cur:
        cur.execute(
            f"""
            SELECT version
            FROM {_MIGRATION_TABLE}
            WHERE service_name = ?
            ORDER BY version ASC
            """,
            (service,),
        )
        rows = cur.fetchall()
    return [str(getattr(row, "version", row[0])) for row in rows]


def _fetch_last_applied_version(client: SqlServerClient, service: str) -> str | None:
    with client.cursor() as cur:
        cur.execute(
            f"""
            SELECT TOP 1 version
            FROM {_MIGRATION_TABLE}
            WHERE service_name = ?
            ORDER BY version DESC
            """,
            (service,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(getattr(row, "version", row[0]))


def _insert_migration_row(
    client: SqlServerClient,
    service: str,
    migration: MigrationFile,
    deployment_id: str | None,
) -> None:
    with client.cursor() as cur:
        cur.execute(
            f"""
            IF NOT EXISTS (
                SELECT 1
                FROM {_MIGRATION_TABLE}
                WHERE service_name = ? AND version = ?
            )
            BEGIN
                INSERT INTO {_MIGRATION_TABLE}
                    (service_name, version, migration_name, checksum_sha256, deployment_id, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
            END
            """,
            (
                service,
                migration.version,
                service,
                migration.version,
                migration.name,
                migration.checksum_sha256,
                deployment_id,
                now_utc(),
            ),
        )


def _versions_after(
    applied_versions: Iterable[str], known_migrations: Iterable[MigrationFile]
) -> list[MigrationFile]:
    applied = set(applied_versions)
    return [m for m in known_migrations if m.version not in applied]


def get_required_schema_version() -> str | None:
    migrations = _list_migration_files()
    if not migrations:
        return None
    return migrations[-1].version


def get_migration_status(
    *,
    client: SqlServerClient,
    service: str,
    required_version: str | None = None,
) -> MigrationStatus:
    _ensure_migration_table(client)
    migrations = _list_migration_files()
    required = required_version or (migrations[-1].version if migrations else "0000")
    applied_versions = _fetch_applied_versions(client, service)
    pending = [m.version for m in _versions_after(applied_versions, migrations)]
    current = _fetch_last_applied_version(client, service)
    compatible = current is not None and current >= required
    return MigrationStatus(
        service=service,
        required_version=required,
        current_version=current,
        pending_versions=pending,
        compatible=compatible,
        last_applied_migration=current,
    )


def run_pending_migrations(
    *,
    client: SqlServerClient,
    service: str,
    deployment_id: str | None,
    lock_timeout_sec: int = 60,
) -> MigrationStatus:
    lock_timeout_ms = max(1000, lock_timeout_sec * 1000)
    _ensure_migration_table(client)
    _acquire_migration_lock(client, service=service, timeout_ms=lock_timeout_ms)
    known_migrations = _list_migration_files()
    applied_versions = _fetch_applied_versions(client, service)
    pending = _versions_after(applied_versions, known_migrations)
    for migration in pending:
        logger.info(
            "Applying migration service=%s version=%s file=%s",
            service,
            migration.version,
            migration.path.name,
        )
        sql_text = migration.path.read_text(encoding="utf-8")
        batches = _split_sql_batches(sql_text)
        for stmt in batches:
            with client.cursor() as cur:
                cur.execute(stmt)
        _insert_migration_row(client, service, migration, deployment_id=deployment_id)
        logger.info("Applied migration service=%s version=%s", service, migration.version)
    return get_migration_status(client=client, service=service)


def ensure_schema_compatibility(
    *,
    client: SqlServerClient,
    service: str,
    required_version: str,
) -> SchemaCompatibilityStatus:
    _ensure_migration_table(client)
    current = _fetch_last_applied_version(client, service)
    compatible = current is not None and current >= required_version
    if compatible:
        return SchemaCompatibilityStatus(
            service=service,
            required_version=required_version,
            current_version=current,
            compatible=True,
            last_applied_migration=current,
            reason=None,
        )
    reason = (
        "no schema migrations applied"
        if current is None
        else f"database schema version {current} is behind required version {required_version}"
    )
    return SchemaCompatibilityStatus(
        service=service,
        required_version=required_version,
        current_version=current,
        compatible=False,
        last_applied_migration=current,
        reason=reason,
    )
