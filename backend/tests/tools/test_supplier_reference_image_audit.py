from __future__ import annotations

from pathlib import Path

from src.tools.supplier_reference_image_audit import (
    KNOWN_INCIDENT_STORAGE_PATH,
    SupplierReferenceImageAuditRow,
    build_known_incident_row,
    executive_status,
    expected_local_path,
    local_file_exists,
    markdown_table_row,
    recommend_recovery,
    render_report_markdown,
    row_is_missing,
)


def test_expected_local_path_under_v3_uploads(tmp_path: Path) -> None:
    path = expected_local_path(tmp_path / "output", "client_suppliers/a/reference_images/x.jpg")
    assert path == tmp_path / "output" / "v3_uploads" / "client_suppliers/a/reference_images/x.jpg"


def test_local_file_exists(tmp_path: Path) -> None:
    output = tmp_path / "output"
    target = output / "v3_uploads" / "uploads" / "x.jpg"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"1")
    assert local_file_exists(output, "uploads/x.jpg")


def test_recommend_recovery_missing_local() -> None:
    assert "re-upload" in recommend_recovery(exists_local=False, exists_remote=None).lower()


def test_row_is_missing_only_when_no_local_and_no_remote() -> None:
    assert row_is_missing(exists_local=False, exists_remote=False)
    assert not row_is_missing(exists_local=True, exists_remote=None)
    assert not row_is_missing(exists_local=False, exists_remote=True)


def test_executive_status_db_failed() -> None:
    assert executive_status(db_error="timeout", rows=[], partial=False) == "DB_QUERY_FAILED"


def test_markdown_table_row_escapes_pipe() -> None:
    row = SupplierReferenceImageAuditRow(
        reference_image_id="id-1",
        client_supplier_id="sup-1",
        provider="local",
        bucket="",
        storage_key_path="client_suppliers/x.jpg",
        filename="x.jpg",
        exists_local=False,
        exists_remote=None,
        recommended_recovery="Re-upload",
        is_missing=True,
    )
    line = markdown_table_row(row)
    assert "id-1" in line
    assert "`client_suppliers/x.jpg`" in line


def test_render_report_includes_known_incident(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    line = build_known_incident_row(
        output_dir=tmp_path,
        exists_local=False,
        exists_remote=None,
        in_db=None,
    )
    md = render_report_markdown(
        generated_at=datetime.now(timezone.utc),
        db_mode="connection_string",
        db_error=None,
        row_count=0,
        rows=[],
        known_incident_line=line,
        output_dir=tmp_path,
    )
    assert KNOWN_INCIDENT_STORAGE_PATH in md
    assert "## 1. Executive summary" in md
