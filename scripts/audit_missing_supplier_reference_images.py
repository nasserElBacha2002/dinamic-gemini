#!/usr/bin/env python3
"""Read-only audit: supplier reference images in DB vs local/remote storage."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

REPORT_PATH = REPO_ROOT / "audit" / "missing-supplier-reference-images-report.md"


def _exists_remote_for_row(
    settings: Any,
    *,
    storage_provider: str | None,
    storage_key: str,
) -> bool | None:
    from src.runtime.container.storage_builders import build_artifact_storage

    key = (storage_key or "").strip()
    if not key:
        return False
    row_prov = (storage_provider or "").strip().lower()
    configured = (settings.artifact_storage_provider or "local").strip().lower()
    prov = row_prov or configured
    if prov == "local":
        return None
    if prov not in ("s3", "gcs"):
        return None
    if row_prov and row_prov != configured:
        return None
    try:
        store = build_artifact_storage(settings)
        return bool(store.object_exists(key))
    except Exception:
        return None


def main() -> int:
    from src.config import load_settings, resolve_sqlserver_connection_config
    from src.database.sqlserver import SqlServerClient
    from src.infrastructure.repositories.sql_supplier_reference_image_repository import (
        _row_to_supplier_reference_image,
    )
    from src.tools.supplier_reference_image_audit import (
        KNOWN_INCIDENT_CLIENT_SUPPLIER_ID,
        KNOWN_INCIDENT_REFERENCE_IMAGE_ID,
        KNOWN_INCIDENT_STORAGE_PATH,
        SupplierReferenceImageAuditRow,
        build_known_incident_row,
        local_file_exists,
        recommend_recovery,
        render_report_markdown,
        row_is_missing,
    )

    settings = load_settings()
    output_dir = Path((settings.output_dir or "output")).resolve()
    rows: list[SupplierReferenceImageAuditRow] = []
    db_error: str | None = None
    db_mode: str | None = None
    in_db_known: bool | None = None

    try:
        sql_res = resolve_sqlserver_connection_config()
        db_mode = sql_res.mode
        connection_string = (sql_res.connection_string or "").strip()
        if not connection_string:
            raise RuntimeError(
                "SQL Server is not configured (empty connection string). "
                "Set SQLSERVER_CONNECTION_STRING or split SQLSERVER_* variables."
            )
        client = SqlServerClient(connection_string)
        with client.cursor() as cur:
            cur.execute(
                """
                SELECT id, client_supplier_id, filename, storage_path,
                       storage_provider, storage_bucket, storage_key, content_type, file_size_bytes, etag,
                       mime_type, file_size, label, description, created_at, updated_at
                FROM supplier_reference_images
                ORDER BY client_supplier_id ASC, created_at ASC, id ASC
                """
            )
            raw_rows = cur.fetchall()

        for db_row in raw_rows:
            img = _row_to_supplier_reference_image(db_row)
            storage_path = (img.storage_path or "").strip()
            storage_key = (img.storage_key or storage_path or "").strip()
            provider = (img.storage_provider or "local").strip() or "local"
            bucket = (img.storage_bucket or "").strip()
            local_ok = local_file_exists(output_dir, storage_path)
            remote_ok = _exists_remote_for_row(
                settings,
                storage_provider=img.storage_provider,
                storage_key=storage_key,
            )
            recovery = recommend_recovery(exists_local=local_ok, exists_remote=remote_ok)
            missing = row_is_missing(exists_local=local_ok, exists_remote=remote_ok)
            if str(img.id) == KNOWN_INCIDENT_REFERENCE_IMAGE_ID:
                in_db_known = True
            rows.append(
                SupplierReferenceImageAuditRow(
                    reference_image_id=str(img.id),
                    client_supplier_id=str(img.client_supplier_id),
                    provider=provider,
                    bucket=bucket,
                    storage_key_path=storage_key or storage_path,
                    filename=(img.filename or "").strip(),
                    exists_local=local_ok,
                    exists_remote=remote_ok,
                    recommended_recovery=recovery,
                    is_missing=missing,
                )
            )
        if in_db_known is None:
            in_db_known = False
    except Exception as exc:
        db_error = str(exc)

    known_local = local_file_exists(output_dir, KNOWN_INCIDENT_STORAGE_PATH)
    known_remote = _exists_remote_for_row(
        settings,
        storage_provider=None,
        storage_key=KNOWN_INCIDENT_STORAGE_PATH,
    )
    known_line = build_known_incident_row(
        output_dir=output_dir,
        exists_local=known_local,
        exists_remote=known_remote,
        in_db=in_db_known,
    )

    report = render_report_markdown(
        generated_at=datetime.now(timezone.utc),
        db_mode=db_mode,
        db_error=db_error,
        row_count=len(rows),
        rows=rows,
        known_incident_line=known_line,
        output_dir=output_dir,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    if db_error:
        print(f"DB query failed: {db_error}", file=sys.stderr)
    missing_count = sum(1 for r in rows if r.is_missing)
    if not known_local:
        missing_count += 1
    print(f"Missing count (approx): {missing_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
