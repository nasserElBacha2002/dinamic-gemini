"""Local CSV secondary key allows multiple D1 products per capture_photo_id."""

from __future__ import annotations

from src.domain.local_csv_import.entities import local_csv_row_secondary_key


def test_two_label_ids_same_photo_are_distinct_secondary_keys() -> None:
    a = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-6",
        label_id="6YD0S6WVMM",
        detection_source="LOCAL_CODE_SCAN",
    )
    b = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-6",
        label_id="6FYR11RPXS",
        detection_source="LOCAL_CODE_SCAN",
    )
    assert a != b
    assert a[1].startswith("label:")
    assert b[1].startswith("label:")


def test_same_label_id_collides_across_photos() -> None:
    a = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-2",
        label_id="LABEL-A",
        detection_source="LOCAL_CODE_SCAN",
    )
    b = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-8",
        label_id="LABEL-A",
        detection_source="LOCAL_CODE_SCAN",
    )
    assert a == b


def test_position_only_key_differs_from_legacy_photo_key() -> None:
    pos = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-1",
        label_id=None,
        detection_source="LOCAL_POSITION_LABEL",
    )
    legacy = local_csv_row_secondary_key(
        capture_session_id="sess",
        capture_photo_id="photo-1",
        label_id=None,
        detection_source="LOCAL_CODE_SCAN",
    )
    assert pos != legacy
