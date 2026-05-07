"""Unit tests for legacy reference migration classifier (C5 dry-run)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_classifier():
    script_path = _BACKEND_ROOT / "scripts" / "legacy_reference_migration_classifier.py"
    spec = importlib.util.spec_from_file_location("legacy_reference_migration_classifier_mod", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cl = _load_classifier()


def _base_row(**kwargs):
    defaults = {
        "id": "ref-1",
        "inventory_id": "inv-1",
        "filename": "a.jpg",
        "storage_path": "inventories/inv-1/visual_references/ref-1.jpg",
        "storage_provider": None,
        "storage_bucket": None,
        "storage_key": None,
        "mime_type": "image/jpeg",
        "file_size": 100,
    }
    defaults.update(kwargs)
    return defaults


def _summary(inv: str, client_id: str | None, supplier_ids: frozenset[str]):
    return cl.InventoryDryRunSummary(
        inventory_id=inv,
        client_id=client_id,
        distinct_aisle_supplier_ids=supplier_ids,
    )


def test_auto_single_supplier():
    row = _base_row()
    summary = _summary("inv-1", "client-a", frozenset({"sup-1"}))
    smap = {"sup-1": "client-a"}
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={"sup-1": frozenset()},
        supplier_client_map=smap,
    )
    assert d.category == cl.MigrationCategory.AUTO_SINGLE_SUPPLIER
    assert d.target_client_supplier_id == "sup-1"


def test_auto_legacy_default_supplier():
    row = _base_row()
    summary = _summary("inv-1", "client-a", frozenset())
    smap = {"sup-def": "client-a"}
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={"client-a": "sup-def"},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map=smap,
    )
    assert d.category == cl.MigrationCategory.AUTO_LEGACY_DEFAULT_SUPPLIER


def test_ambiguous_no_supplier_no_default():
    row = _base_row()
    summary = _summary("inv-1", "client-a", frozenset())
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={},
    )
    assert d.category == cl.MigrationCategory.AMBIGUOUS_NO_SUPPLIER


def test_ambiguous_multi_supplier():
    row = _base_row()
    summary = _summary("inv-1", "client-a", frozenset({"sup-1", "sup-2"}))
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={"sup-1": "client-a", "sup-2": "client-a"},
    )
    assert d.category == cl.MigrationCategory.AMBIGUOUS_MULTI_SUPPLIER


def test_ambiguous_missing_client():
    row = _base_row()
    summary = _summary("inv-1", None, frozenset())
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={},
    )
    assert d.category == cl.MigrationCategory.AMBIGUOUS_MISSING_CLIENT


def test_skip_missing_storage():
    row = _base_row(storage_path="", storage_provider=None)
    summary = _summary("inv-1", "client-a", frozenset({"sup-1"}))
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={"sup-1": "client-a"},
    )
    assert d.category == cl.MigrationCategory.SKIP_MISSING_STORAGE


def test_skip_invalid_row_missing_inventory_join():
    row = _base_row()
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=True,
        inventory_summary=_summary("inv-1", "client-a", frozenset({"sup-1"})),
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={"sup-1": "client-a"},
    )
    assert d.category == cl.MigrationCategory.SKIP_INVALID_ROW


def test_skip_already_migrated_heuristic():
    row = _base_row(id="ref-x")
    summary = _summary("inv-1", "client-a", frozenset({"sup-1"}))
    pairs = frozenset({("sup-1", "inventories/inv-1/visual_references/ref-1.jpg")})
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=pairs,
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={"sup-1": "client-a"},
    )
    assert d.category == cl.MigrationCategory.SKIP_ALREADY_MIGRATED


@pytest.mark.parametrize(
    "mime",
    ["application/pdf", "image/gif"],
)
def test_skip_invalid_mime(mime: str):
    row = _base_row(mime_type=mime)
    summary = _summary("inv-1", "client-a", frozenset({"sup-1"}))
    d = cl.classify_legacy_reference_row(
        row=row,
        inventory_missing=False,
        inventory_summary=summary,
        legacy_default_supplier_by_client={},
        accept_default_supplier_fallback=True,
        migrated_pairs_paths=frozenset(),
        migrated_pairs_keys=frozenset(),
        existing_filenames_by_supplier={},
        supplier_client_map={"sup-1": "client-a"},
    )
    assert d.category == cl.MigrationCategory.SKIP_INVALID_ROW
