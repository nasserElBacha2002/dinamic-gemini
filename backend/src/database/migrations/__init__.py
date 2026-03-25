"""Versioned DB migration and schema compatibility utilities."""

from .service import (
    MigrationStatus,
    SchemaCompatibilityError,
    SchemaCompatibilityStatus,
    ensure_schema_compatibility,
    get_migration_status,
    run_pending_migrations,
)

__all__ = [
    "MigrationStatus",
    "SchemaCompatibilityError",
    "SchemaCompatibilityStatus",
    "ensure_schema_compatibility",
    "get_migration_status",
    "run_pending_migrations",
]
