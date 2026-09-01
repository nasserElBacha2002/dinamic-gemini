"""Productive SEGMENTED extraction profiles for ClientSupplier pruebas b (c314c8c3…).

Shared by operational correction scripts and regression tests so persisted config
matches validated fixtures exactly.
"""

from __future__ import annotations

from src.domain.client_supplier.extraction_profile import (
    CONFIGURATION_SCHEMA_VERSION_V2,
    DeterministicBarcodeRules,
    ExtractionProfileConfiguration,
    FieldMappingRule,
    FieldMappingSource,
    PayloadStructure,
    QuantityExtractionRules,
    QuantityPresence,
    RecognitionMode,
)


def pruebas_b_item_segmented_configuration() -> ExtractionProfileConfiguration:
    """ITEM QR: LPNA000184|SKU773421|24"""
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        recognition_mode=RecognitionMode.FULL,
        semantic_type="PRODUCT_SKU",
        required_fields=("label_id", "sku", "quantity"),
        accepted_barcode_formats=("QR", "CODE128"),
        quantity_rules=QuantityExtractionRules(
            required=True,
            minimum=1,
            expected_presence=QuantityPresence.ALWAYS,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="LPNA",
            exact_length=None,
            min_length=None,
            max_length=None,
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=3,
            field_mappings=(
                FieldMappingRule("label_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("sku", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("quantity", FieldMappingSource.SEGMENT, 2),
            ),
        ),
    )


def pruebas_b_position_segmented_configuration() -> ExtractionProfileConfiguration:
    """POSITION QR: A04-R-02|04|RIGHT|02"""
    return ExtractionProfileConfiguration(
        configuration_schema_version=CONFIGURATION_SCHEMA_VERSION_V2,
        recognition_mode=RecognitionMode.FULL,
        semantic_type="LOCATION",
        required_fields=("position_id",),
        accepted_barcode_formats=("QR", "CODE128"),
        quantity_rules=QuantityExtractionRules(
            required=False,
            expected_presence=QuantityPresence.OPTIONAL,
        ),
        deterministic=DeterministicBarcodeRules(
            expected_prefix="A04",
            exact_length=None,
            min_length=None,
            max_length=None,
            payload_structure=PayloadStructure.SEGMENTED,
            delimiter="|",
            expected_segment_count=4,
            field_mappings=(
                FieldMappingRule("position_id", FieldMappingSource.SEGMENT, 0),
                FieldMappingRule("pallet", FieldMappingSource.SEGMENT, 1),
                FieldMappingRule("side", FieldMappingSource.SEGMENT, 2),
                FieldMappingRule("level", FieldMappingSource.SEGMENT, 3),
            ),
        ),
    )


def pruebas_b_item_configuration_dict() -> dict:
    return pruebas_b_item_segmented_configuration().to_public_dict()


def pruebas_b_position_configuration_dict() -> dict:
    return pruebas_b_position_segmented_configuration().to_public_dict()


__all__ = [
    "pruebas_b_item_configuration_dict",
    "pruebas_b_item_segmented_configuration",
    "pruebas_b_position_configuration_dict",
    "pruebas_b_position_segmented_configuration",
]
