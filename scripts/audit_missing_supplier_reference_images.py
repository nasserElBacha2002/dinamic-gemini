#!/usr/bin/env python3
"""Read-only audit: supplier reference images in DB vs local/remote storage."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

REPORT_PATH = REPO_ROOT / "audit" / "missing-supplier-reference-images-report.md"


def _exists_local(output_dir: Path, storage_path: str) -> bool:
    rel = (storage_path or "").strip().lstrip("/")
    if not rel:
        return False
    candidate = output_dir / "v3_uploads" / rel
    return candidate.is_file()


def _exists_remote(settings, storage_path: str) -> bool | None:
    provider = (settings.artifact_storage_provider or "local").strip().lower()
    if provider == "local":
        return None
    try:
        from src.runtime.container.storage_builders import build_artifact_storage

        store = build_artifact_storage(settings)
        return bool(store.object_exists(storage_path))
    except Exception:
        return None


def main() -> int:
    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient

    settings = load_settings()
    output_dir = Path(settings.output_dir or "output").resolve()
    rows: list[dict[str, str | bool | None]] = []
    db_error: str | None = None

    try:
        client = SqlServerClient(settings.require_sqlserver_connection_string())
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
        from src.infrastructure.repositories.sql_supplier_reference_image_repository import (
            _row_to_supplier_reference_image,
        )

        images = [_row_to_supplier_reference_image(row) for row in raw_rows]
        for img in images:
            storage_path = (img.storage_path or "").strip()
            storage_key = (img.storage_key or storage_path or "").strip()
            local_ok = _exists_local(output_dir, storage_path)
            remote_ok = _exists_remote(settings, storage_key or storage_path)
            if local_ok and (remote_ok is True or remote_ok is None):
                recovery = "OK"
            elif not local_ok and remote_ok is True:
                recovery = "Repair local metadata or re-download; object exists remotely"
            elif not local_ok and remote_ok is False:
                recovery = "Restore from backup or re-upload via supplier reference UI"
            elif not local_ok and remote_ok is None:
                recovery = "Re-upload via supplier reference UI or restore local file under v3_uploads"
            else:
                recovery = "Review storage_provider metadata"
            rows.append(
                {
                    "id": str(img.id),
                    "client_supplier_id": str(img.client_supplier_id),
                    "expected": storage_key or storage_path,
                    "local": local_ok,
                    "remote": remote_ok,
                    "recovery": recovery,
                }
            )
    except Exception as exc:
        db_error = str(exc)

    lines = [
        "# Missing supplier reference images — audit report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    if db_error:
        lines.extend(
            [
                "## Database",
                "",
                f"Could not query `supplier_reference_images`: `{db_error}`",
                "",
                "Run this script with SQL Server available (same env as the API) to populate the table.",
                "",
            ]
        )
    lines.extend(
        [
            "## Known incident (manual)",
            "",
            "| Reference image id | Client supplier id | Expected path/key | Exists local | Exists remote | Recommended recovery |",
            "| --- | --- | --- | ---: | ---: | --- |",
            "| 065b9151-ed44-4377-94ba-41e79894a0b3 | f7f2b112-ad3e-48d0-aa03-aa95dceff896 | "
            "`client_suppliers/f7f2b112-ad3e-48d0-aa03-aa95dceff896/reference_images/"
            "065b9151-ed44-4377-94ba-41e79894a0b3.jpg` | no (reported) | unknown | "
            "Re-upload via admin supplier reference UI or restore file under "
            f"`{output_dir}/v3_uploads/...` |",
            "",
        ]
    )
    if rows:
        lines.extend(
            [
                "## Database rows",
                "",
                "| Reference image id | Client supplier id | Expected path/key | Exists local | Exists remote | Recommended recovery |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in rows:
            local_cell = "yes" if row["local"] else "no"
            if row["remote"] is True:
                remote_cell = "yes"
            elif row["remote"] is False:
                remote_cell = "no"
            else:
                remote_cell = "n/a"
            lines.append(
                f"| {row['id']} | {row['client_supplier_id']} | `{row['expected']}` | "
                f"{local_cell} | {remote_cell} | {row['recovery']} |"
            )
        lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
