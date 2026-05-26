"""Pure helpers for supplier reference image storage audit (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

KNOWN_INCIDENT_REFERENCE_IMAGE_ID = "065b9151-ed44-4377-94ba-41e79894a0b3"
KNOWN_INCIDENT_CLIENT_SUPPLIER_ID = "f7f2b112-ad3e-48d0-aa03-aa95dceff896"
KNOWN_INCIDENT_STORAGE_PATH = (
    f"client_suppliers/{KNOWN_INCIDENT_CLIENT_SUPPLIER_ID}/reference_images/"
    f"{KNOWN_INCIDENT_REFERENCE_IMAGE_ID}.jpg"
)

ExecutiveStatus = Literal[
    "NO_MISSING_REFERENCE_IMAGES_FOUND",
    "MISSING_REFERENCE_IMAGES_FOUND",
    "DB_QUERY_FAILED",
    "PARTIAL_REPORT_GENERATED",
]

SUPPLIER_REFERENCE_IMAGES_TABLE = "supplier_reference_images"


@dataclass(frozen=True)
class SupplierReferenceImageAuditRow:
    reference_image_id: str
    client_supplier_id: str
    provider: str
    bucket: str
    storage_key_path: str
    filename: str
    exists_local: bool
    exists_remote: bool | None
    recommended_recovery: str
    is_missing: bool


def normalize_storage_path(storage_path: str) -> str:
    return (storage_path or "").strip().lstrip("/").replace("\\", "/")


def expected_local_path(output_dir: Path, storage_path: str) -> Path:
    rel = normalize_storage_path(storage_path)
    return output_dir / "v3_uploads" / rel


def local_file_exists(output_dir: Path, storage_path: str) -> bool:
    return expected_local_path(output_dir, storage_path).is_file()


def recommend_recovery(*, exists_local: bool, exists_remote: bool | None) -> str:
    if exists_local and (exists_remote is True or exists_remote is None):
        return "OK"
    if not exists_local and exists_remote is True:
        return "Repair local metadata or re-download; object exists remotely"
    if not exists_local and exists_remote is False:
        return "Restore from backup or re-upload via supplier reference UI"
    if not exists_local and exists_remote is None:
        return "Re-upload via supplier reference UI or restore local file under v3_uploads"
    return "Review storage_provider metadata"


def row_is_missing(*, exists_local: bool, exists_remote: bool | None) -> bool:
    if exists_local:
        return False
    if exists_remote is True:
        return False
    return True


def executive_status(
    *,
    db_error: str | None,
    rows: list[SupplierReferenceImageAuditRow],
    partial: bool,
) -> ExecutiveStatus:
    if db_error and not rows:
        return "DB_QUERY_FAILED"
    if partial:
        return "PARTIAL_REPORT_GENERATED"
    missing = [r for r in rows if r.is_missing]
    if not missing:
        return "NO_MISSING_REFERENCE_IMAGES_FOUND"
    return "MISSING_REFERENCE_IMAGES_FOUND"


def _remote_cell(exists_remote: bool | None) -> str:
    if exists_remote is True:
        return "yes"
    if exists_remote is False:
        return "no"
    return "n/a"


def markdown_table_row(row: SupplierReferenceImageAuditRow) -> str:
    return (
        f"| {row.reference_image_id} | {row.client_supplier_id} | {row.provider} | "
        f"{row.bucket or '—'} | `{row.storage_key_path}` | "
        f"{'yes' if row.exists_local else 'no'} | {_remote_cell(row.exists_remote)} | "
        f"{row.recommended_recovery} |"
    )


def build_known_incident_row(
    *,
    output_dir: Path,
    exists_local: bool,
    exists_remote: bool | None,
    in_db: bool | None,
) -> str:
    db_note = "yes" if in_db is True else "no" if in_db is False else "unknown"
    recovery = recommend_recovery(exists_local=exists_local, exists_remote=exists_remote)
    if not exists_local:
        recovery = (
            f"{recovery}; re-upload via supplier reference UI or restore under "
            f"`{output_dir}/v3_uploads/{KNOWN_INCIDENT_STORAGE_PATH}`"
        )
    return (
        f"| {KNOWN_INCIDENT_REFERENCE_IMAGE_ID} | {KNOWN_INCIDENT_CLIENT_SUPPLIER_ID} | "
        f"(see DB) | — | `{KNOWN_INCIDENT_STORAGE_PATH}` | "
        f"{'yes' if exists_local else 'no'} | {_remote_cell(exists_remote)} | "
        f"{recovery} (in DB: {db_note}) |"
    )


def render_report_markdown(
    *,
    generated_at: datetime,
    db_mode: str | None,
    db_error: str | None,
    row_count: int,
    rows: list[SupplierReferenceImageAuditRow],
    known_incident_line: str,
    output_dir: Path,
) -> str:
    status = executive_status(
        db_error=db_error,
        rows=rows,
        partial=bool(db_error and rows),
    )
    missing_rows = [r for r in rows if r.is_missing]
    lines = [
        "# Missing supplier reference images — audit report",
        "",
        f"Generated: {generated_at.astimezone(timezone.utc).isoformat()}",
        "",
        "## 1. Executive summary",
        "",
        f"**Status:** `{status}`",
        "",
        f"- Rows audited: {row_count}",
        f"- Missing (local and remote unavailable): {len(missing_rows)}",
        "",
        "## 2. Database query status",
        "",
    ]
    if db_error:
        lines.extend(
            [
                f"- **Result:** failed — `{db_error}`",
                f"- **Table:** `{SUPPLIER_REFERENCE_IMAGES_TABLE}`",
                "- **Credentials:** not logged",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- **Connection mode:** `{db_mode or 'unknown'}`",
                f"- **Table:** `{SUPPLIER_REFERENCE_IMAGES_TABLE}`",
                f"- **Row count:** {row_count}",
                "",
            ]
        )

    lines.extend(
        [
            "## 3. Missing supplier reference images",
            "",
            "| Reference image id | Client supplier id | Provider | Bucket | Storage key/path | "
            "Exists local | Exists remote | Recommended recovery |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    if missing_rows:
        for row in missing_rows:
            lines.append(markdown_table_row(row))
    else:
        lines.append("| — | — | — | — | — | — | — | No missing rows detected. |")
    lines.extend(
        [
            "",
            "## 4. Known incident",
            "",
            "| Reference image id | Client supplier id | Expected path/key | Exists local | "
            "Exists remote | Recommended recovery |",
            "| --- | --- | --- | ---: | ---: | --- |",
            known_incident_line,
            "",
            "## 5. Recommended recovery",
            "",
            "- Re-upload through the client supplier reference image UI.",
            "- Restore from backup to the expected local path under `v3_uploads/`.",
            "- If the object exists in GCS/S3 but DB still says `local`, repair DB metadata.",
            "- If the DB row exists but both local and remote are missing, manual re-upload is required.",
            "",
            f"Local output root: `{output_dir}`",
            "",
        ]
    )
    if rows and not missing_rows:
        lines.extend(
            [
                "## All audited rows (OK)",
                "",
                "| Reference image id | Client supplier id | Provider | Bucket | Storage key/path | "
                "Exists local | Exists remote | Recommended recovery |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for row in rows:
            lines.append(markdown_table_row(row))
        lines.append("")
    return "\n".join(lines)
