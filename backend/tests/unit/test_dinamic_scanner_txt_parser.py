from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.services.dinamic_scanner_txt_parser import (
    aisle_code_from_txt_filename,
    parse_dinamic_scanner_txt,
)
from src.domain.dinamic_scanner_txt.errors import (
    TXT_EMPTY,
    DinamicScannerTxtImportError,
)
from src.domain.product_labels.format import build_product_label_payload

_VECTORS = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "product-labels"
    / "v1"
    / "checksum-vectors.json"
)


def _load_vectors() -> dict:
    return json.loads(_VECTORS.read_text(encoding="utf-8"))


def _valid_d1_line(label_id: str = "A1B2C3D4E5", sku: str = "SKU001", qty: int = 100) -> str:
    return build_product_label_payload(label_id=label_id, internal_code=sku, quantity=qty)


def _txt(*lines: str) -> bytes:
    return "\n".join(lines).encode()


def test_parser_single_product_with_position() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(),
        )
    )

    assert len(parsed.positions) == 1
    assert parsed.positions[0].label_id == "POS001"
    assert parsed.positions[0].side == "RIGHT"
    assert parsed.products[0].position is parsed.positions[0]
    assert parsed.products[0].errors == ()


def test_parser_multiple_products_same_position() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100),
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU002", qty=50),
        )
    )

    assert all(product.position is parsed.positions[0] for product in parsed.products)


def test_parser_position_change() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100),
            "POSITION|POS002|05|LEFT",
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU002", qty=50),
        )
    )

    assert parsed.products[0].position is parsed.positions[0]
    assert parsed.products[1].position is parsed.positions[1]


def test_parser_invalid_position_resets_active_context() -> None:
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "POSITION|POS001|04|RIGHT",
            _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU1", qty=10),
            "POSITION|MALFORMADA",
            _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU2", qty=20),
            "POSITION|POS002|05|LEFT",
            _valid_d1_line(label_id="STVWXYZ234", sku="SKU3", qty=30),
        )
    )

    assert parsed.products[0].position.label_id == "POS001"
    assert parsed.products[1].position is None
    assert "product:no_valid_active_position" in parsed.products[1].errors
    assert parsed.products[2].position.label_id == "POS002"


def test_parser_rejects_invalid_side() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS1|04|CENTER"))
    assert parsed.positions == ()
    assert any("side:invalid" in warning for warning in parsed.parse_warnings)


def test_parser_accepts_position_label_id_at_canonical_limit() -> None:
    parsed = parse_dinamic_scanner_txt(_txt(f"POSITION|{'L' * 64}|PALLET-01|LEFT"))

    assert parsed.positions[0].label_id == "L" * 64
    assert parsed.positions[0].pallet == "PALLET-01"


def test_parser_rejects_position_label_id_above_canonical_limit() -> None:
    parsed = parse_dinamic_scanner_txt(_txt(f"POSITION|{'L' * 65}|PALLET-01|LEFT"))

    assert parsed.positions == ()
    assert any("position_label_id:too_long" in warning for warning in parsed.parse_warnings)


def test_parser_accepts_pallet_without_position_identity_length_rule() -> None:
    pallet = "P" * 65
    parsed = parse_dinamic_scanner_txt(_txt(f"POSITION|POS1|{pallet}|LEFT"))

    assert parsed.positions[0].pallet == pallet


def test_parser_rejects_pallet_format_character() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS1|PAL\u200bLET|LEFT"))

    assert parsed.positions == ()
    assert any("pallet:control_character" in warning for warning in parsed.parse_warnings)


def test_parser_rejects_position_label_format_character() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS\u200b1|PALLET-01|LEFT"))

    assert parsed.positions == ()
    assert any(
        "position_label_id:control_character" in warning for warning in parsed.parse_warnings
    )


def test_parser_product_before_position_is_rejected() -> None:
    parsed = parse_dinamic_scanner_txt(_txt(_valid_d1_line()))
    assert "product:no_valid_active_position" in parsed.products[0].errors


def test_parser_invalid_line_is_warning() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("INVALID"))
    assert parsed.products == ()
    assert any("unknown_record" in warning for warning in parsed.parse_warnings)


def test_parser_empty_file_raises() -> None:
    with pytest.raises(DinamicScannerTxtImportError) as exc:
        parse_dinamic_scanner_txt(b"   \n  ")
    assert exc.value.code == TXT_EMPTY


def test_aisle_code_from_filename_strips_extension() -> None:
    assert aisle_code_from_txt_filename("Pasillo_A_04.txt") == "Pasillo_A_04"


def test_aisle_code_rejects_path_traversal() -> None:
    with pytest.raises(DinamicScannerTxtImportError):
        aisle_code_from_txt_filename("../secret.txt")


def test_parser_pipe_item_without_validation_context_is_not_accepted() -> None:
    """Transport recognition alone must not invent a valid ITEM without profiles."""
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "ASI-DDWDD8|48",
            "ASI-LDFMEE|10",
            "ASI-U59KNU|8",
        )
    )
    assert parsed.products == ()
    assert any("pipe_item_requires_validation_context" in w for w in parsed.parse_warnings)


def _product_sku_pipe_item_config(*, expected_prefix: str):
    from dataclasses import replace

    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        DeterministicBarcodeRules,
        FieldMappingRule,
        FieldMappingSource,
        ItemLabelSemanticType,
        QuantityExtractionRules,
        QuantityPresence,
        RecognitionMode,
        minimal_supplier_item_configuration,
    )

    return replace(
        minimal_supplier_item_configuration(
            expected_prefix=expected_prefix,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
        ),
        recognition_mode=RecognitionMode.FULL,
        required_fields=("sku",),
        semantic_type=ItemLabelSemanticType.PRODUCT_SKU.value,
        quantity_rules=QuantityExtractionRules(
            required=False,
            minimum=1,
            expected_presence=QuantityPresence.OPTIONAL,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix=expected_prefix,
            character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
            field_mappings=(FieldMappingRule("sku", FieldMappingSource.WHOLE, None),),
        ),
    )


def test_parser_real_raspberry_pipe_items_without_position_via_profile() -> None:
    """Real Raspberry file shape: identifier|qty only — no POSITION header."""
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        minimal_supplier_position_configuration,
    )

    item = _product_sku_pipe_item_config(expected_prefix="ASI-")
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    parsed = parse_dinamic_scanner_txt(
        _txt(
            "ASI-DDWDD8|48",
            "ASI-LDFMEE|10",
            "ASI-U59KNU|8",
        ),
        item_configuration=item,
        position_configuration=position,
    )
    assert parsed.positions == ()
    assert len(parsed.products) == 3
    assert parsed.products[0].internal_code == "ASI-DDWDD8"
    assert parsed.products[0].quantity == 48
    assert parsed.products[0].label_id == ""
    assert "product:no_valid_active_position" not in parsed.products[0].errors
    assert parsed.products[0].errors == ()
    assert parsed.products[1].internal_code == "ASI-LDFMEE"
    assert parsed.products[2].internal_code == "ASI-U59KNU"


def test_parser_pipe_item_validated_via_supplier_profile_identifier() -> None:
    """Profile validates identifier; pipe quantity is transport (no hardcoded ASI rules)."""
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        minimal_supplier_position_configuration,
    )

    item = _product_sku_pipe_item_config(expected_prefix="ASI-")
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    parsed = parse_dinamic_scanner_txt(
        _txt("LOC-A01-02", "ASI-DDWDD8|48", "ASI-DDWDD8|12"),
        item_configuration=item,
        position_configuration=position,
    )
    assert len(parsed.positions) == 1
    assert len(parsed.products) == 2
    assert all(p.label_id == "" for p in parsed.products)
    assert parsed.products[0].internal_code == "ASI-DDWDD8"
    assert parsed.products[0].quantity == 48
    assert parsed.products[1].internal_code == "ASI-DDWDD8"
    assert parsed.products[1].quantity == 12


def test_parser_invalid_pipe_identifier_rejected_via_profile() -> None:
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        minimal_supplier_position_configuration,
    )

    item = _product_sku_pipe_item_config(expected_prefix="ASI-")
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    parsed = parse_dinamic_scanner_txt(
        _txt("ASI-DDWDD8|48", "WRONG-CODE|10"),
        item_configuration=item,
        position_configuration=position,
    )
    assert len(parsed.products) == 1
    assert parsed.products[0].internal_code == "ASI-DDWDD8"
    assert any("pipe_identifier" in w for w in parsed.parse_warnings)


def test_parser_repeated_sku_not_deduped_product_sku_semantic() -> None:
    from src.domain.client_supplier.extraction_profile import (
        CharacterSetPolicy,
        minimal_supplier_position_configuration,
    )

    item = _product_sku_pipe_item_config(expected_prefix="SKU")
    position = minimal_supplier_position_configuration(
        expected_prefix="LOC",
        exact_length=10,
        character_set=CharacterSetPolicy.ALPHANUMERIC_WITH_HYPHEN,
    )
    parsed = parse_dinamic_scanner_txt(
        _txt("LOC-A01-02", "SKU-111|5", "SKU-111|7"),
        item_configuration=item,
        position_configuration=position,
    )
    assert len(parsed.products) == 2
    assert parsed.products[0].internal_code == "SKU-111"
    assert parsed.products[1].internal_code == "SKU-111"


def test_parser_duplicate_unique_label_id_deduped_once() -> None:
    line = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100)
    parsed = parse_dinamic_scanner_txt(
        _txt("POSITION|POS001|04|RIGHT", line, line)
    )
    assert len(parsed.products) == 1
    assert parsed.products[0].label_id == "A1B2C3D4E5"
    assert any("duplicate_unique_label_id" in w for w in parsed.parse_warnings)


def test_parser_same_label_id_different_sku_is_conflict() -> None:
    a = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100)
    b = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU002", qty=100)
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", a, b))
    assert len(parsed.products) == 2
    assert parsed.products[0].errors == ()
    assert "unique_label_id:identity_conflict" in parsed.products[1].errors
    assert any("unique_label_id_identity_conflict" in w for w in parsed.parse_warnings)


def test_parser_same_label_id_different_quantity_is_conflict() -> None:
    a = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100)
    b = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=50)
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", a, b))
    assert len(parsed.products) == 2
    assert parsed.products[0].errors == ()
    assert "unique_label_id:identity_conflict" in parsed.products[1].errors


def test_parser_invalid_d1_does_not_reserve_label_id_for_later_valid() -> None:
    vectors = _load_vectors()
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    # Ensure bad and good share the same label_id when possible; rebuild good from bad parts.
    parts = bad.split("|")
    assert len(parts) >= 4
    label_id = parts[1]
    good = _valid_d1_line(label_id=label_id, sku="SKU001", qty=100)
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", bad, good))
    assert len(parsed.products) == 2
    assert "d1:checksum_failed" in parsed.products[0].errors
    assert parsed.products[1].errors == ()
    assert parsed.products[1].label_id == label_id.upper()
    assert not any("duplicate_unique_label_id" in w for w in parsed.parse_warnings)


def test_parser_same_sku_distinct_d1_label_ids_kept() -> None:
    a = _valid_d1_line(label_id="A1B2C3D4E5", sku="SKU001", qty=100)
    b = _valid_d1_line(label_id="FGHJKMNPQR", sku="SKU001", qty=50)
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", a, b))
    assert len(parsed.products) == 2
    assert parsed.products[0].label_id == "A1B2C3D4E5"
    assert parsed.products[1].label_id == "FGHJKMNPQR"
    assert parsed.products[0].internal_code == "SKU001"
    assert parsed.products[1].internal_code == "SKU001"


def test_parser_existing_position_format_still_works() -> None:
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", _valid_d1_line()))
    assert parsed.positions[0].label_id == "POS001"
    assert parsed.products[0].errors == ()


def test_parser_d1_without_position_still_errors() -> None:
    parsed = parse_dinamic_scanner_txt(_txt(_valid_d1_line()))
    assert "product:no_valid_active_position" in parsed.products[0].errors


def test_txt_valid_d1_accepted() -> None:
    line = _valid_d1_line()
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", line))
    assert parsed.products[0].errors == ()


def test_txt_checksum_invalid_rejected() -> None:
    vectors = _load_vectors()
    bad = next(
        v["tampered_payload"]
        for v in vectors["vectors"]
        if v["name"] == "checksum-fail-tampered-qty"
    )
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", bad))
    assert "d1:checksum_failed" in parsed.products[0].errors


def test_txt_malformed_d1_rejected() -> None:
    vectors = _load_vectors()
    raw = next(v["raw"] for v in vectors["vectors"] if v["name"] == "malformed-grammar-bad-label")
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", raw))
    assert "d1:malformed" in parsed.products[0].errors


def test_txt_d2_rejected() -> None:
    vectors = _load_vectors()
    raw = next(v["raw"] for v in vectors["vectors"] if v["name"] == "unknown-version-d2")
    parsed = parse_dinamic_scanner_txt(_txt("POSITION|POS001|04|RIGHT", raw))
    assert "d1:unknown_version" in parsed.products[0].errors
