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


class LabelBackgroundHint(str, Enum):
    LIGHT = "LIGHT"
    DARK = "DARK"
    VARIABLE = "VARIABLE"
    DISABLED = "DISABLED"


class LabelShapeHint(str, Enum):
    RECTANGULAR = "RECTANGULAR"
    APPROXIMATELY_RECTANGULAR = "APPROXIMATELY_RECTANGULAR"
    VARIABLE = "VARIABLE"


class LabelOrientationHint(str, Enum):
    HORIZONTAL = "HORIZONTAL"
    VERTICAL = "VERTICAL"
    SQUARE_OR_VERTICAL = "SQUARE_OR_VERTICAL"
    ANY = "ANY"


class AnchorMatchPolicy(str, Enum):
    """How strictly label candidates must match OCR anchors."""

    ANCHORS_REQUIRED = "ANCHORS_REQUIRED"
    ANCHORS_PREFERRED = "ANCHORS_PREFERRED"
    GEOMETRY_ONLY_ALLOWED = "GEOMETRY_ONLY_ALLOWED"


class UnanchoredCodeCandidatePolicy(str, Enum):
    """Policy for strong numeric codes that lack a matched label anchor."""

    REJECT = "REJECT"
    ALLOW_FOR_MANUAL_REVIEW = "ALLOW_FOR_MANUAL_REVIEW"
    ALLOW_IF_UNIQUE_AND_STRONG = "ALLOW_IF_UNIQUE_AND_STRONG"


class QuantityPresence(str, Enum):
    ALWAYS = "ALWAYS"
    OPTIONAL = "OPTIONAL"
    UNKNOWN = "UNKNOWN"


class MissingQuantityAction(str, Enum):
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"
    EXTERNAL_FALLBACK = "EXTERNAL_FALLBACK"
    UNRECOGNIZED = "UNRECOGNIZED"
    # RESOLVE_CODE_ONLY reserved — not enabled by default (domain requires qty).
    RESOLVE_CODE_ONLY = "RESOLVE_CODE_ONLY"


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
class LabelDetectionRules:
    """Section A — how to locate the inventory label inside a pallet photo.

    Defaults are **supplier-agnostic** (not specialized for 7-digit inventory labels).
    """

    enabled: bool = True
    expected_background: LabelBackgroundHint = LabelBackgroundHint.VARIABLE
    expected_shape: LabelShapeHint = LabelShapeHint.APPROXIMATELY_RECTANGULAR
    expected_orientation: LabelOrientationHint = LabelOrientationHint.ANY
    primary_anchors: tuple[str, ...] = ()
    secondary_anchors: tuple[str, ...] = ()
    minimum_anchor_matches: int = 0
    anchor_match_policy: AnchorMatchPolicy = AnchorMatchPolicy.GEOMETRY_ONLY_ALLOWED
    minimum_relative_area: float = 0.005
    maximum_relative_area: float = 0.45
    allow_rotation: bool = True
    # Deskew (small-angle Hough). Not a full perspective/homography transform.
    allow_deskew: bool = True
    # Kept for backward-compatible payloads; mapped to allow_deskew when parsing.
    allow_perspective_correction: bool = True
    allow_full_image_fallback: bool = True
    maximum_candidate_regions: int = 8


@dataclass(frozen=True)
class InternalCodeSourceRule:
    field_key: str
    priority: int
    enabled: bool = True
    allowed_as_internal_code: bool = True
    requires_label: bool = False
    pattern: str | None = None
    aliases: tuple[str, ...] = ()
    allowed_spatial_relations: tuple[str, ...] = ()
    maximum_anchor_distance_ratio: float | None = None


@dataclass(frozen=True)
class QuantityExtractionRules:
    aliases: tuple[str, ...] = ("CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES", "CANT. TOTAL")
    required: bool = True
    data_type: FieldDataType = FieldDataType.INTEGER
    minimum: int = 1
    maximum: int = 99_999_999
    allow_decimals: bool = False
    allow_negative: bool = False
    default_value: int | None = None  # must remain None for automatic resolution
    accepted_units: tuple[str, ...] = ()
    expected_presence: QuantityPresence = QuantityPresence.ALWAYS
    missing_quantity_action: MissingQuantityAction = (
        MissingQuantityAction.PENDING_MANUAL_REVIEW
    )
    allow_external_fallback: bool = True
    allowed_spatial_relations: tuple[str, ...] = (
        SpatialRelation.BELOW.value,
        SpatialRelation.RIGHT_OF.value,
        SpatialRelation.NEAR.value,
    )
    maximum_anchor_distance_ratio: float | None = 0.25


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
    exact_length: int | None = None
    allow_letters: bool = True
    allow_digits: bool = True
    allow_hyphen: bool = True
    allow_slash: bool = True
    allow_spaces: bool = False
    preserve_leading_zeros: bool = True
    regex: str | None = None
    reject_measurement_patterns: bool = True
    unanchored_candidate_policy: UnanchoredCodeCandidatePolicy = (
        UnanchoredCodeCandidatePolicy.REJECT
    )


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
    label_detection_rules: LabelDetectionRules = field(default_factory=LabelDetectionRules)
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
    # Only the system default may enable this; custom profiles must stay False.
    allow_unconfigured_code_source_fallback: bool = False

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
                    "aliases": list(s.aliases),
                    "allowed_spatial_relations": list(s.allowed_spatial_relations),
                    "maximum_anchor_distance_ratio": s.maximum_anchor_distance_ratio,
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
                "expected_presence": self.quantity_rules.expected_presence.value,
                "missing_quantity_action": self.quantity_rules.missing_quantity_action.value,
                "allow_external_fallback": self.quantity_rules.allow_external_fallback,
                "allowed_spatial_relations": list(
                    self.quantity_rules.allowed_spatial_relations
                ),
                "maximum_anchor_distance_ratio": (
                    self.quantity_rules.maximum_anchor_distance_ratio
                ),
            },
            "label_detection_rules": {
                "enabled": self.label_detection_rules.enabled,
                "expected_background": self.label_detection_rules.expected_background.value,
                "expected_shape": self.label_detection_rules.expected_shape.value,
                "expected_orientation": self.label_detection_rules.expected_orientation.value,
                "primary_anchors": list(self.label_detection_rules.primary_anchors),
                "secondary_anchors": list(self.label_detection_rules.secondary_anchors),
                "minimum_anchor_matches": self.label_detection_rules.minimum_anchor_matches,
                "anchor_match_policy": self.label_detection_rules.anchor_match_policy.value,
                "minimum_relative_area": self.label_detection_rules.minimum_relative_area,
                "maximum_relative_area": self.label_detection_rules.maximum_relative_area,
                "allow_rotation": self.label_detection_rules.allow_rotation,
                "allow_deskew": self.label_detection_rules.allow_deskew,
                "allow_perspective_correction": (
                    self.label_detection_rules.allow_deskew
                ),
                "allow_full_image_fallback": (
                    self.label_detection_rules.allow_full_image_fallback
                ),
                "maximum_candidate_regions": (
                    self.label_detection_rules.maximum_candidate_regions
                ),
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
                    "exact_length": self.validation_rules.code.exact_length,
                    "allow_letters": self.validation_rules.code.allow_letters,
                    "allow_digits": self.validation_rules.code.allow_digits,
                    "allow_hyphen": self.validation_rules.code.allow_hyphen,
                    "allow_slash": self.validation_rules.code.allow_slash,
                    "allow_spaces": self.validation_rules.code.allow_spaces,
                    "preserve_leading_zeros": self.validation_rules.code.preserve_leading_zeros,
                    "regex": self.validation_rules.code.regex,
                    "reject_measurement_patterns": (
                        self.validation_rules.code.reject_measurement_patterns
                    ),
                    "unanchored_candidate_policy": (
                        self.validation_rules.code.unanchored_candidate_policy.value
                    ),
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
            "allow_unconfigured_code_source_fallback": (
                self.allow_unconfigured_code_source_fallback
            ),
        }


def default_extraction_configuration() -> ExtractionProfileConfiguration:
    """Conservative system default — not specialized for any supplier label layout."""
    return ExtractionProfileConfiguration(
        internal_code_sources=(
            InternalCodeSourceRule("INTERNAL_CODE", priority=1, enabled=True),
            InternalCodeSourceRule("EAN", priority=2, enabled=True),
            InternalCodeSourceRule("ARTICLE", priority=3, enabled=True),
        ),
        quantity_rules=QuantityExtractionRules(
            aliases=("CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES"),
            required=True,
            data_type=FieldDataType.INTEGER,
            allow_decimals=False,
            minimum=1,
            default_value=None,
            expected_presence=QuantityPresence.ALWAYS,
            missing_quantity_action=MissingQuantityAction.PENDING_MANUAL_REVIEW,
        ),
        validation_rules=ExtractionValidationRules(
            code=CodeValidationRules(
                min_length=1,
                max_length=128,
                exact_length=None,
                allow_letters=True,
                allow_digits=True,
                allow_hyphen=True,
                allow_slash=True,
                allow_spaces=False,
                preserve_leading_zeros=True,
                reject_measurement_patterns=True,
            )
        ),
        label_detection_rules=LabelDetectionRules(),
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
        allow_unconfigured_code_source_fallback=True,
    )


def inventory_seven_digit_internal_code_template() -> ExtractionProfileConfiguration:
    """Opt-in template: light inventory label with numeric internal code of length 7.

    Never applied automatically — callers must select it explicitly.
    """
    base = default_extraction_configuration()
    return ExtractionProfileConfiguration(
        internal_code_sources=(
            InternalCodeSourceRule(
                "INTERNAL_CODE",
                priority=1,
                enabled=True,
                aliases=("CÓDIGO INTERNO", "CODIGO INTERNO", "COD. INTERNO"),
                allowed_spatial_relations=(
                    SpatialRelation.BELOW.value,
                    SpatialRelation.SAME_COLUMN.value,
                    SpatialRelation.NEAR.value,
                ),
            ),
            InternalCodeSourceRule("EAN", priority=2, enabled=False),
            InternalCodeSourceRule("ARTICLE", priority=3, enabled=False),
        ),
        quantity_rules=QuantityExtractionRules(
            aliases=("CANT. TOTAL", "CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES"),
            required=True,
            data_type=FieldDataType.INTEGER,
            allow_decimals=False,
            minimum=1,
            default_value=None,
            expected_presence=QuantityPresence.ALWAYS,
            missing_quantity_action=MissingQuantityAction.PENDING_MANUAL_REVIEW,
            allow_external_fallback=True,
        ),
        validation_rules=ExtractionValidationRules(
            code=CodeValidationRules(
                min_length=7,
                max_length=7,
                exact_length=7,
                allow_letters=False,
                allow_digits=True,
                allow_hyphen=False,
                allow_slash=False,
                allow_spaces=False,
                preserve_leading_zeros=True,
                reject_measurement_patterns=True,
                unanchored_candidate_policy=UnanchoredCodeCandidatePolicy.ALLOW_FOR_MANUAL_REVIEW,
            ),
            ean=base.validation_rules.ean,
            quantity_integer_only=True,
        ),
        label_detection_rules=LabelDetectionRules(
            enabled=True,
            expected_background=LabelBackgroundHint.LIGHT,
            expected_shape=LabelShapeHint.APPROXIMATELY_RECTANGULAR,
            expected_orientation=LabelOrientationHint.ANY,
            primary_anchors=("CÓDIGO INTERNO", "CODIGO INTERNO", "COD. INTERNO"),
            secondary_anchors=("INVENTARIO GENERAL", "CANT. TOTAL", "CANTIDAD"),
            minimum_anchor_matches=1,
            anchor_match_policy=AnchorMatchPolicy.ANCHORS_PREFERRED,
            allow_rotation=True,
            allow_deskew=True,
            allow_perspective_correction=True,
            allow_full_image_fallback=True,
        ),
        aliases={
            **base.aliases,
            "quantity": ("CANT. TOTAL", "CANTIDAD", "CANT.", "QTY", "QUANTITY", "UNIDADES"),
        },
        required_fields=("internal_code", "quantity"),
        allow_unconfigured_code_source_fallback=False,
        accepted_barcode_formats=base.accepted_barcode_formats,
        qr_payload_formats=base.qr_payload_formats,
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
    "AnchorMatchPolicy",
    "CodeValidationRules",
    "EanValidationRules",
    "ExtractionProfileConfiguration",
    "ExtractionProfileStatus",
    "ExtractionValidationRules",
    "FieldDataType",
    "INTERNAL_CODE_SOURCE_KEYS",
    "InternalCodeSourceRule",
    "LabelBackgroundHint",
    "LabelDetectionRules",
    "LabelOrientationHint",
    "LabelShapeHint",
    "MissingQuantityAction",
    "QrPayloadFormat",
    "QuantityExtractionRules",
    "QuantityPresence",
    "ReferenceAnnotation",
    "SUPPORTED_BARCODE_FORMATS",
    "SpatialRelation",
    "SupplierExtractionProfile",
    "UnanchoredCodeCandidatePolicy",
    "default_extraction_configuration",
    "inventory_seven_digit_internal_code_template",
]
