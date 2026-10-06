"""Representative GET .../recognition-config JSON (OfflineRecognitionBundleResponse shape)."""

from __future__ import annotations

from typing import Any


def sample_recognition_config_bundle() -> dict[str, Any]:
    return {
        "bundle_schema_version": 1,
        "inventory_id": "inv-uuid-1",
        "client_id": "client-uuid-1",
        "generated_at": "2026-01-15T12:00:00+00:00",
        "aisles": [
            {
                "aisle_id": "aisle-uuid-a1",
                "aisle_code": "A1",
                "client_supplier_id": "supplier-uuid-1",
                "item_profile_source_override": "SUPPLIER",
                "position_profile_source_override": None,
                "effective_item_source": "SUPPLIER",
                "effective_position_source": "DINAMIC",
            },
            {
                "aisle_id": "aisle-uuid-b2",
                "aisle_code": "B2",
                "client_supplier_id": None,
                "item_profile_source_override": None,
                "position_profile_source_override": None,
                "effective_item_source": "DINAMIC",
                "effective_position_source": "DINAMIC",
            },
            {
                "aisle_id": "aisle-uuid-skip",
                "aisle_code": None,
                "client_supplier_id": "supplier-uuid-2",
                "effective_item_source": "DINAMIC",
                "effective_position_source": "DINAMIC",
            },
        ],
        "suppliers": [
            {
                "client_supplier_id": "supplier-uuid-1",
                "item_source": "SUPPLIER",
                "position_source": "DINAMIC",
            }
        ],
        "profiles": [
            {
                "client_supplier_id": "supplier-uuid-1",
                "label_kind": "ITEM",
                "source": "SUPPLIER",
                "profile_id": "profile-item-1",
                "profile_version": 1,
                "configuration_schema_version": 2,
                "recognition_mode": "SEGMENTED",
                "semantic_type": None,
                "configuration": {"segments": []},
            }
        ],
        "bundle_revision": "2026-01-15T12:00:00+00:00+1",
    }
