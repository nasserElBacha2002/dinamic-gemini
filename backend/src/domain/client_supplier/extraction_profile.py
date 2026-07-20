"""Phase 6 — SupplierExtractionProfile domain + typed configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ExtractionProfileStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUPERSEDED = "SUPERSEDED"


class FieldDataType(str, Enum):
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    CODE = "CODE"
    BOOLEAN = "BOOLEAN"


class SpatialRelation(str, Enum):
    RIGHT_OF = "RIGHT_OF"
    LEFT_OF = "LEFT_OF"
    ABOVE = "ABOVE"
    BELOW = "BELOW"
    SAME_ROW = "SAME_ROW"
    SAME_COLUMN = "SAME_COLUMN"
    SAME_CELL = "SAME_CELL"
    NEAR = "NEAR"
    INSIDE_REGION = "INSIDE_REGION"


class QrPayloadFormat(str, Enum):
    PLAIN_CODE = "PLAIN_CODE"
    CODE_QUANTITY_PIPE = "CODE_QUANTITY_PIPE"
    DI1 = "DI1"
    JSON = "JSON"
    LABELED = "LABELED"
    CUSTOM_PATTERN = "CUSTOM_PATTERN"


# Scanner formats actually supported by the current CODE_SCAN path (pyzbar).
SUPPORTED_BARCODE_FORMATS: frozenset[str] = frozenset(
    {"QR", "CODE128", "EAN8", "EAN13", "UPC_A", "CODE39", "I25", "PDF417", "DATABAR"}
)

INTERNAL_CODE_SOURCE_KEYS: tuple[str, ...] = (
    "EAN",
    "INTERNAL_CODE",
    "ARTICLE",
    "SKU",
    "PRODUCT",
)


@dataclass(frozen=True)
class InternalCodeSourceRule:
    field_key: str
    priority: int
    enabled: bool = True
    allowed_as_internal_code: bool = True
    requires_label: bool = False
    pattern: str | None = None


@dataclass(frozen=True)
class QuantityExtractionRules:
    aliases: tuple[str, ...] = ("CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES")
    required: bool = True
    data_type: FieldDataType = FieldDataType.INTEGER
    minimum: int = 1
    maximum: int = 99_999_999
    allow_decimals: bool = False
    allow_negative: bool = False
    default_value: int | None = None  # must remain None for automatic resolution
    accepted_units: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdditionalFieldRule:
    field_key: str
    display_name: str
    aliases: tuple[str, ...] = ()
    data_type: FieldDataType = FieldDataType.TEXT
    required: bool = False
    priority: int = 100
    normalization_rule: str | None = None
    validation_rule: str | None = None


@dataclass(frozen=True)
class CodeValidationRules:
    min_length: int = 1
    max_length: int = 128
    allow_letters: bool = True
    allow_digits: bool = True
    allow_hyphen: bool = True
    allow_slash: bool = True
    allow_spaces: bool = False
    preserve_leading_zeros: bool = True
    regex: str | None = None


@dataclass(frozen=True)
class EanValidationRules:
    allow_ean8: bool = True
    allow_ean12: bool = True
    allow_ean13: bool = True
    allow_ean14: bool = True
    validate_checksum: bool = True


@dataclass(frozen=True)
class ExtractionValidationRules:
    code: CodeValidationRules = field(default_factory=CodeValidationRules)
    ean: EanValidationRules = field(default_factory=EanValidationRules)
    quantity_integer_only: bool = True


@dataclass(frozen=True)
class ExtractionProfileConfiguration:
    """Structured extraction rules — source of truth (not free-text prompts)."""

    internal_code_sources: tuple[InternalCodeSourceRule, ...] = ()
    forbidden_internal_code_sources: tuple[str, ...] = ()
    quantity_rules: QuantityExtractionRules = field(default_factory=QuantityExtractionRules)
    additional_fields: tuple[AdditionalFieldRule, ...] = ()
    validation_rules: ExtractionValidationRules = field(
        default_factory=ExtractionValidationRules
    )
    accepted_barcode_formats: tuple[str, ...] = ("QR", "CODE128", "EAN13", "EAN8", "UPC_A")
    qr_payload_formats: tuple[str, ...] = (
        QrPayloadFormat.PLAIN_CODE.value,
        QrPayloadFormat.CODE_QUANTITY_PIPE.value,
        QrPayloadFormat.DI1.value,
        QrPayloadFormat.LABELED.value,
    )
    custom_payload_pattern: str | None = None
    required_fields: tuple[str, ...] = ("internal_code", "quantity")
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "internal_code_sources": [
                {
                    "field_key": s.field_key,
                    "priority": s.priority,
                    "enabled": s.enabled,
                    "allowed_as_internal_code": s.allowed_as_internal_code,
                    "requires_label": s.requires_label,
                    "pattern": s.pattern,
                }
                for s in self.internal_code_sources
            ],
            "forbidden_internal_code_sources": list(self.forbidden_internal_code_sources),
            "quantity_rules": {
                "aliases": list(self.quantity_rules.aliases),
                "required": self.quantity_rules.required,
                "data_type": self.quantity_rules.data_type.value,
                "minimum": self.quantity_rules.minimum,
                "maximum": self.quantity_rules.maximum,
                "allow_decimals": self.quantity_rules.allow_decimals,
                "allow_negative": self.quantity_rules.allow_negative,
                "default_value": self.quantity_rules.default_value,
                "accepted_units": list(self.quantity_rules.accepted_units),
            },
            "additional_fields": [
                {
                    "field_key": f.field_key,
                    "display_name": f.display_name,
                    "aliases": list(f.aliases),
                    "data_type": f.data_type.value,
                    "required": f.required,
                    "priority": f.priority,
                    "normalization_rule": f.normalization_rule,
                    "validation_rule": f.validation_rule,
                }
                for f in self.additional_fields
            ],
            "validation_rules": {
                "code": {
                    "min_length": self.validation_rules.code.min_length,
                    "max_length": self.validation_rules.code.max_length,
                    "allow_letters": self.validation_rules.code.allow_letters,
                    "allow_digits": self.validation_rules.code.allow_digits,
                    "allow_hyphen": self.validation_rules.code.allow_hyphen,
                    "allow_slash": self.validation_rules.code.allow_slash,
                    "allow_spaces": self.validation_rules.code.allow_spaces,
                    "preserve_leading_zeros": self.validation_rules.code.preserve_leading_zeros,
                    "regex": self.validation_rules.code.regex,
                },
                "ean": {
                    "allow_ean8": self.validation_rules.ean.allow_ean8,
                    "allow_ean12": self.validation_rules.ean.allow_ean12,
                    "allow_ean13": self.validation_rules.ean.allow_ean13,
                    "allow_ean14": self.validation_rules.ean.allow_ean14,
                    "validate_checksum": self.validation_rules.ean.validate_checksum,
                },
                "quantity_integer_only": self.validation_rules.quantity_integer_only,
            },
            "accepted_barcode_formats": list(self.accepted_barcode_formats),
            "qr_payload_formats": list(self.qr_payload_formats),
            "custom_payload_pattern": self.custom_payload_pattern,
            "required_fields": list(self.required_fields),
            "aliases": {k: list(v) for k, v in self.aliases.items()},
        }


def default_extraction_configuration() -> ExtractionProfileConfiguration:
    """Conservative system default when no supplier profile is active."""
    return ExtractionProfileConfiguration(
        internal_code_sources=(
            InternalCodeSourceRule("INTERNAL_CODE", priority=1),
            InternalCodeSourceRule("EAN", priority=2),
            InternalCodeSourceRule("ARTICLE", priority=3),
        ),
        quantity_rules=QuantityExtractionRules(
            aliases=("CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES"),
            required=True,
            minimum=1,
            default_value=None,
        ),
        aliases={
            "internal_code": (
                "CÓDIGO INTERNO",
                "CODIGO INTERNO",
                "CÓD.",
                "COD",
                "SKU",
                "INTERNAL_CODE",
            ),
            "ean": ("EAN", "EAN13", "CÓDIGO EAN", "CODIGO EAN"),
            "article": ("ARTÍCULO", "ARTICULO", "ARTICLE"),
            "quantity": ("CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES"),
        },
        required_fields=("internal_code", "quantity"),
    )


@dataclass
class SupplierExtractionProfile:
    """Versioned extraction profile scoped to client_id + supplier (client_supplier)."""

    id: str
    client_id: str
    supplier_id: str  # client_suppliers.id
    profile_key: str
    version: int
    status: ExtractionProfileStatus
    configuration: ExtractionProfileConfiguration
    visual_notes: str | None
    created_by: str | None
    created_at: datetime
    activated_by: str | None = None
    activated_at: datetime | None = None
    superseded_at: datetime | None = None
    updated_at: datetime | None = None
    row_version: int = 1

    @property
    def is_active(self) -> bool:
        return self.status is ExtractionProfileStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.id or not str(self.id).strip():
            raise ValueError("SupplierExtractionProfile.id is required")
        if not self.client_id or not str(self.client_id).strip():
            raise ValueError("SupplierExtractionProfile.client_id is required")
        if not self.supplier_id or not str(self.supplier_id).strip():
            raise ValueError("SupplierExtractionProfile.supplier_id is required")
        if self.version is None or int(self.version) < 1:
            raise ValueError("SupplierExtractionProfile.version must be >= 1")
        if self.configuration.quantity_rules.default_value is not None:
            raise ValueError(
                "quantity_rules.default_value must be null for automatic resolution"
            )


@dataclass(frozen=True)
class ReferenceAnnotation:
    id: str
    template_image_id: str
    profile_id: str | None
    field_key: str
    anchor_texts: tuple[str, ...]
    spatial_relation: SpatialRelation
    normalized_polygon: tuple[tuple[float, float], ...] | None
    priority: int = 1
    required: bool = False
    max_distance_ratio: float | None = None


__all__ = [
    "AdditionalFieldRule",
    "CodeValidationRules",
    "EanValidationRules",
    "ExtractionProfileConfiguration",
    "ExtractionProfileStatus",
    "ExtractionValidationRules",
    "FieldDataType",
    "INTERNAL_CODE_SOURCE_KEYS",
    "InternalCodeSourceRule",
    "QrPayloadFormat",
    "QuantityExtractionRules",
    "ReferenceAnnotation",
    "SUPPORTED_BARCODE_FORMATS",
    "SpatialRelation",
    "SupplierExtractionProfile",
    "default_extraction_configuration",
]
