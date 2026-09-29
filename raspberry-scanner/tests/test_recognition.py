import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.models import RecognitionProfile, RecognitionSnapshot
from config.repository import SnapshotRepository
from config.service import ConfigService
from recognition import RecognitionService, SelectionError, _dinamic, _supplier


def profile(kind: str, configuration: dict[str, object], schema: int = 2) -> RecognitionProfile:
    return RecognitionProfile.from_dict({
        "client_supplier_id": "supplier-a", "label_kind": kind,
        "source": "SUPPLIER", "profile_id": f"{kind.lower()}-profile",
        "profile_version": 1, "configuration_schema_version": schema,
        "recognition_mode": "MINIMAL", "semantic_type": "LPN",
        "configuration": configuration,
    })


def d1(label_id: str = "0123456789", code: str = "SKU", quantity: int = 1) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    body = f"D1|{label_id}|{code}|{quantity}"
    checksum = sum(
        ((alphabet.index(char) if char in alphabet else ord(char) % 36) * (index + 1))
        for index, char in enumerate(body.upper())
    ) % 36
    return f"{body}|{alphabet[checksum]}"


def source_snapshot(item_source: str, position_source: str) -> RecognitionSnapshot:
    profiles = []
    for kind, source in (("ITEM", item_source), ("POSITION", position_source)):
        if source == "SUPPLIER":
            profiles.append({
                "client_supplier_id": "s", "label_kind": kind, "source": "SUPPLIER",
                "profile_id": f"{kind.lower()}-p", "profile_version": 1,
                "configuration_schema_version": 2, "recognition_mode": "MINIMAL",
                "semantic_type": None,
                "configuration": {"deterministic": {"payload_structure": "SIMPLE"}},
            })
    return RecognitionSnapshot.from_dict({
        "bundle_schema_version": 1, "generated_at": "2026-01-01T00:00:00Z", "bundle_revision": f"{item_source}-{position_source}",
        "clients": [{"client_id": "c", "name": "C", "bundle_revision": "c1", "suppliers": [{
            "client_supplier_id": "s", "name": "S", "item_source": item_source, "position_source": position_source,
        }], "profiles": profiles}],
    })


def snapshot() -> RecognitionSnapshot:
    return RecognitionSnapshot.from_dict({
        "bundle_schema_version": 1, "generated_at": "2026-01-01T00:00:00Z", "bundle_revision": "r1",
        "clients": [
            {"client_id": "a", "name": "A", "bundle_revision": "a1", "suppliers": [
                {"client_supplier_id": "supplier-a", "name": "Supplier A", "item_source": "SUPPLIER", "position_source": "DINAMIC"},
            ], "profiles": [{
                "client_supplier_id": "supplier-a", "label_kind": "ITEM", "source": "SUPPLIER", "profile_id": "item-profile", "profile_version": 1, "configuration_schema_version": 2,
                "recognition_mode": "MINIMAL", "semantic_type": "LPN",
                "configuration": {"recognition_mode": "MINIMAL", "deterministic": {"payload_structure": "SIMPLE", "expected_prefix": "SKU-", "character_set": "ALPHANUMERIC_WITH_HYPHEN"}, "required_fields": ["label_id"]},
            }]},
            {"client_id": "b", "name": "B", "bundle_revision": "b1", "suppliers": [
                {"client_supplier_id": "supplier-b", "name": "Supplier B", "item_source": "DINAMIC", "position_source": "DINAMIC"},
            ], "profiles": []},
        ],
    })


class RecognitionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        path = Path(tempfile.mkdtemp()) / "snapshot.json"
        self.service = ConfigService(SnapshotRepository(path), None)
        self.service._snapshot = snapshot()
        self.recognition = RecognitionService(self.service)

    def test_all_is_raw_and_never_tries_supplier_profiles(self) -> None:
        self.recognition.select("a", None, scanning=False)
        result = self.recognition.process("wrong-value")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["classification"], "RAW")
        self.assertEqual(result["recognition"]["selection_mode"], "ALL")

    def test_specific_resolves_item_and_position_independently(self) -> None:
        selected = self.recognition.select("a", "supplier-a", scanning=False)
        self.assertEqual(selected["item_source"], "SUPPLIER")
        self.assertEqual(selected["position_source"], "DINAMIC")
        item = self.recognition.process("SKU-123")
        self.assertTrue(item["accepted"])
        self.assertEqual(item["classification"], "ITEM")
        self.assertEqual(item["recognition"]["results"]["ITEM"]["profile_id"], "item-profile")
        position = self.recognition.process('{"type":"DINAMIC_POSITION","version":1,"label_id":"P-1"}')
        self.assertTrue(position["accepted"])
        self.assertEqual(position["classification"], "POSITION")
        self.assertEqual(position["recognition"]["results"]["POSITION"]["source"], "DINAMIC")

    def test_all_four_source_combinations_keep_each_kind_independent(self) -> None:
        for item_source, position_source in (
            ("SUPPLIER", "SUPPLIER"), ("SUPPLIER", "DINAMIC"),
            ("DINAMIC", "SUPPLIER"), ("DINAMIC", "DINAMIC"),
        ):
            with self.subTest(item_source=item_source, position_source=position_source):
                self.service._snapshot = source_snapshot(item_source, position_source)
                self.recognition.select("c", "s", scanning=False)
                result = self.recognition.process(d1())
                outcomes = result["recognition"]["results"]
                self.assertEqual(outcomes["ITEM"]["source"], item_source)
                self.assertEqual(outcomes["POSITION"]["source"], position_source)

    def test_supplier_item_does_not_revive_d1_and_ambiguity_matches_mobile_rule(self) -> None:
        self.service._snapshot = source_snapshot("SUPPLIER", "SUPPLIER")
        self.recognition.select("c", "s", scanning=False)
        d1_result = self.recognition.process(d1())
        self.assertEqual(d1_result["classification"], "POSITION")
        self.assertEqual(
            d1_result["recognition"]["results"]["ITEM"]["error_code"],
            "DINAMIC_D1_RESERVED",
        )
        ambiguous = self.recognition.process("supplier-only")
        self.assertTrue(ambiguous["accepted"])
        self.assertEqual(ambiguous["classification"], "AMBIGUOUS")

    def test_cross_client_supplier_and_active_scan_changes_are_rejected(self) -> None:
        with self.assertRaisesRegex(SelectionError, "supplier_not_found_for_client"):
            self.recognition.select("a", "supplier-b", scanning=False)
        with self.assertRaisesRegex(SelectionError, "selection_locked_while_scanning"):
            self.recognition.select("a", None, scanning=True)

    def test_changing_client_resets_supplier_to_all_when_requested(self) -> None:
        self.recognition.select("a", "supplier-a", scanning=False)
        selected = self.recognition.select("b", None, scanning=False)
        self.assertEqual(selected["client_id"], "b")
        self.assertIsNone(selected["supplier_id"])

    def test_supplier_segmented_matches_mobile_structural_then_field_normalization(self) -> None:
        configured = profile("ITEM", {
            "configuration_schema_version": 2,
            "deterministic": {
                "payload_structure": "SEGMENTED", "delimiter": "|",
                "expected_segment_count": 2,
                "normalization": {"remove_internal_spaces": True, "case_normalization": "UPPER"},
                "field_mappings": [
                    {"source": "SEGMENT", "segment_index": 0, "target": "label_id"},
                    {"source": "SEGMENT", "segment_index": 1, "target": "quantity"},
                ],
            },
            "required_fields": ["label_id", "quantity"],
            "quantity_rules": {"minimum": 1, "maximum": 9},
        })
        result = _supplier(" ab 12 | 2 ", "ITEM", configured)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["value"], "AB12")
        self.assertEqual(_supplier("AB12|2|extra", "ITEM", configured)["error_code"], "LABEL_SEGMENT_COUNT_MISMATCH")
        self.assertEqual(_supplier("AB12|0", "ITEM", configured)["status"], "INVALID")

    def test_supplier_segmented_requires_mapped_identity_and_explicitly_rejects_bad_config(self) -> None:
        no_identity = profile("ITEM", {
            "deterministic": {"payload_structure": "SEGMENTED", "field_mappings": []},
        })
        self.assertEqual(_supplier("value|other", "ITEM", no_identity)["status"], "INVALID")
        malformed = profile("ITEM", {"deterministic": {"payload_structure": "SIMPLE", "field_mappings": "wrong"}})
        self.assertEqual(_supplier("SKU", "ITEM", malformed)["status"], "CONFIGURATION_INVALID")
        unsupported = profile("ITEM", {"deterministic": {"payload_structure": "GS1"}})
        self.assertEqual(_supplier("010123", "ITEM", unsupported)["status"], "UNRESOLVED_OFFLINE")

    def test_dinamic_d1_and_position_follow_existing_parser_boundaries(self) -> None:
        self.assertEqual(_dinamic(d1(), "ITEM")["status"], "VALID")
        self.assertEqual(_dinamic(d1()[:-1] + "0", "ITEM")["status"], "INVALID")
        self.assertEqual(_dinamic("D1|bad", "ITEM")["error_code"], "D1_MALFORMED")
        self.assertEqual(_dinamic("not-a-label", "ITEM")["status"], "NOT_APPLICABLE")
        valid_v2 = '{"type":"DINAMIC_POSITION","version":2,"label_id":"P1","pallet":"PAL","side":"LEFT","level":1,"marker_index":1,"marker_total":1}'
        self.assertEqual(_dinamic(valid_v2, "POSITION")["status"], "VALID")
        invalid_v2 = valid_v2.replace('"pallet":"PAL"', '"pallet":""')
        self.assertEqual(_dinamic(invalid_v2, "POSITION")["status"], "INVALID")

    def test_missing_supplier_after_snapshot_replacement_fails_closed(self) -> None:
        self.recognition.select("a", "supplier-a", scanning=False)
        self.service._snapshot = RecognitionSnapshot.from_dict({
            "bundle_schema_version": 1, "generated_at": "2026-01-01T00:00:00Z", "bundle_revision": "r2",
            "clients": [{"client_id": "a", "name": "A", "bundle_revision": "a2", "suppliers": [], "profiles": []}],
        })
        result = self.recognition.process("anything")
        self.assertFalse(result["accepted"])
        self.assertEqual(result["classification"], "CONFIGURATION_INVALID")
        self.assertEqual(result["recognition"]["selection_mode"], "SPECIFIC")


if __name__ == "__main__":
    unittest.main()
