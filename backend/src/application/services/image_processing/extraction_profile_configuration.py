"""Parse / serialize ExtractionProfileConfiguration JSON (Phase 6)."""

from __future__ import annotations

from typing import Any

from src.domain.client_supplier.extraction_profile import (
    INTERNAL_CODE_SOURCE_KEYS,
    SUPPORTED_BARCODE_FORMATS,
    AdditionalFieldRule,
    CodeValidationRules,
    EanValidationRules,
    ExtractionProfileConfiguration,
    ExtractionValidationRules,
    FieldDataType,
    InternalCodeSourceRule,
    LabelBackgroundHint,
    LabelDetectionRules,
    LabelOrientationHint,
    LabelShapeHint,
    MissingQuantityAction,
    QuantityExtractionRules,
    QuantityPresence,
    AnchorMatchPolicy,
    default_extraction_configuration,
)

_MAX_REGEX_LEN = 200
_MAX_ALIAS_LEN = 64
_MAX_ALIASES = 40


class ExtractionProfileConfigurationError(ValueError):
    """Typed configuration validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _as_str_tuple(raw: object, *, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ExtractionProfileConfigurationError(
            "INVALID_ALIASES", f"{field} must be a list of strings"
        )
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ExtractionProfileConfigurationError(
                "INVALID_ALIASES", f"{field} entries must be strings"
            )
        text = item.strip()
        if not text:
            raise ExtractionProfileConfigurationError(
                "EMPTY_ALIAS", f"{field} contains an empty alias"
            )
        if len(text) > _MAX_ALIAS_LEN:
            raise ExtractionProfileConfigurationError(
                "ALIAS_TOO_LONG", f"{field} alias exceeds {_MAX_ALIAS_LEN} chars"
            )
        out.append(text)
    if len(out) > _MAX_ALIASES:
        raise ExtractionProfileConfigurationError(
            "TOO_MANY_ALIASES", f"{field} exceeds {_MAX_ALIASES} aliases"
        )
    return tuple(out)


def _parse_data_type(raw: object, *, field: str) -> FieldDataType:
    key = str(raw or "TEXT").strip().upper()
    try:
        return FieldDataType(key)
    except ValueError as exc:
        raise ExtractionProfileConfigurationError(
            "UNSUPPORTED_FIELD_TYPE", f"{field} has unsupported type {key!r}"
        ) from exc


def _reject_custom_regex(pattern: str | None, *, field: str) -> None:
    """Custom regex is withdrawn for this phase (ReDoS / worker safety)."""
    if pattern is None:
        return
    text = str(pattern).strip()
    if not text:
        return
    raise ExtractionProfileConfigurationError(
        "REGEX_NOT_SUPPORTED",
        f"{field}: custom regex is not supported in this phase; remove regex/pattern",
    )


def _validate_optional_regex(pattern: str | None) -> str | None:
    # Kept for call-site compatibility; always rejects non-empty patterns.
    _reject_custom_regex(pattern, field="regex")
    return None


def parse_extraction_configuration(
    raw: dict[str, Any] | None,
) -> ExtractionProfileConfiguration:
    if not raw:
        return default_extraction_configuration()
    if not isinstance(raw, dict):
        raise ExtractionProfileConfigurationError(
            "PROFILE_INVALID", "configuration_json must be an object"
        )

    sources_raw = raw.get("internal_code_sources") or []
    if not isinstance(sources_raw, list):
        raise ExtractionProfileConfigurationError(
            "PROFILE_INVALID", "internal_code_sources must be a list"
        )
    sources: list[InternalCodeSourceRule] = []
    seen_priorities: set[int] = set()
    seen_keys: set[str] = set()
    for item in sources_raw:
        if not isinstance(item, dict):
            raise ExtractionProfileConfigurationError(
                "PROFILE_INVALID", "internal_code_sources entries must be objects"
            )
        key = str(item.get("field_key") or "").strip().upper()
        if key not in INTERNAL_CODE_SOURCE_KEYS:
            raise ExtractionProfileConfigurationError(
                "UNKNOWN_CODE_SOURCE", f"unknown internal_code source {key!r}"
            )
        if key in seen_keys:
            raise ExtractionProfileConfigurationError(
                "DUPLICATE_CODE_SOURCE", f"duplicate internal_code source {key!r}"
            )
        priority = int(item.get("priority") or 0)
        if priority < 1:
            raise ExtractionProfileConfigurationError(
                "INVALID_PRIORITY", "priority must be >= 1"
            )
        if priority in seen_priorities:
            raise ExtractionProfileConfigurationError(
                "DUPLICATE_PRIORITY", f"duplicate priority {priority}"
            )
        seen_keys.add(key)
        seen_priorities.add(priority)
        if item.get("pattern"):
            _reject_custom_regex(str(item.get("pattern")), field=f"internal_code_sources.{key}.pattern")
        sources.append(
            InternalCodeSourceRule(
                field_key=key,
                priority=priority,
                enabled=bool(item.get("enabled", True)),
                allowed_as_internal_code=bool(item.get("allowed_as_internal_code", True)),
                requires_label=bool(item.get("requires_label", False)),
                pattern=None,
                aliases=_as_str_tuple(item.get("aliases"), field=f"internal_code_sources.{key}.aliases"),
                allowed_spatial_relations=tuple(
                    str(x).strip().upper()
                    for x in (item.get("allowed_spatial_relations") or [])
                    if str(x).strip()
                ),
                maximum_anchor_distance_ratio=(
                    float(item["maximum_anchor_distance_ratio"])
                    if item.get("maximum_anchor_distance_ratio") is not None
                    else None
                ),
            )
        )
    sources_sorted = tuple(sorted(sources, key=lambda s: s.priority))

    forbidden = tuple(
        str(x).strip().upper()
        for x in (raw.get("forbidden_internal_code_sources") or [])
        if str(x).strip()
    )
    for f in forbidden:
        if f not in INTERNAL_CODE_SOURCE_KEYS:
            raise ExtractionProfileConfigurationError(
                "UNKNOWN_CODE_SOURCE", f"unknown forbidden source {f!r}"
            )

    qty_raw: dict[str, Any] = (
        raw["quantity_rules"] if isinstance(raw.get("quantity_rules"), dict) else {}
    )
    default_value = qty_raw.get("default_value", None)
    if default_value is not None:
        raise ExtractionProfileConfigurationError(
            "QUANTITY_DEFAULT_FORBIDDEN",
            "quantity default_value is forbidden for automatic resolution (must be null)",
        )
    qty = QuantityExtractionRules(
        aliases=_as_str_tuple(qty_raw.get("aliases"), field="quantity_rules.aliases")
        or QuantityExtractionRules().aliases,
        required=bool(qty_raw.get("required", True)),
        data_type=_parse_data_type(qty_raw.get("data_type"), field="quantity_rules.data_type"),
        minimum=int(qty_raw["minimum"] if qty_raw.get("minimum") is not None else 1),
        maximum=int(
            qty_raw["maximum"] if qty_raw.get("maximum") is not None else 99_999_999
        ),
        allow_decimals=bool(qty_raw.get("allow_decimals", False)),
        allow_negative=bool(qty_raw.get("allow_negative", False)),
        default_value=None,
        accepted_units=_as_str_tuple(
            qty_raw.get("accepted_units"), field="quantity_rules.accepted_units"
        ),
        expected_presence=_parse_quantity_presence(qty_raw.get("expected_presence")),
        missing_quantity_action=_parse_missing_quantity_action(
            qty_raw.get("missing_quantity_action")
        ),
        allow_external_fallback=bool(qty_raw.get("allow_external_fallback", True)),
        allowed_spatial_relations=tuple(
            str(x).strip().upper()
            for x in (
                qty_raw.get("allowed_spatial_relations")
                or QuantityExtractionRules().allowed_spatial_relations
            )
            if str(x).strip()
        ),
        maximum_anchor_distance_ratio=(
            float(qty_raw["maximum_anchor_distance_ratio"])
            if qty_raw.get("maximum_anchor_distance_ratio") is not None
            else QuantityExtractionRules().maximum_anchor_distance_ratio
        ),
    )
    if qty.allow_negative or qty.minimum < 1:
        raise ExtractionProfileConfigurationError(
            "INVALID_QUANTITY_RULES",
            "quantity must require minimum >= 1 and disallow negatives",
        )
    if qty.maximum < qty.minimum:
        raise ExtractionProfileConfigurationError(
            "INVALID_QUANTITY_RULES", "quantity maximum must be >= minimum"
        )
    if qty.allow_decimals or qty.data_type is FieldDataType.DECIMAL:
        raise ExtractionProfileConfigurationError(
            "QUANTITY_DECIMALS_NOT_SUPPORTED",
            "quantity_rules.allow_decimals / DECIMAL are not supported; use INTEGER only",
        )
    # Force integer domain regardless of payload.
    qty = QuantityExtractionRules(
        aliases=qty.aliases,
        required=qty.required,
        data_type=FieldDataType.INTEGER,
        minimum=qty.minimum,
        maximum=qty.maximum,
        allow_decimals=False,
        allow_negative=False,
        default_value=None,
        accepted_units=qty.accepted_units,
        expected_presence=qty.expected_presence,
        missing_quantity_action=qty.missing_quantity_action,
        allow_external_fallback=qty.allow_external_fallback,
        allowed_spatial_relations=qty.allowed_spatial_relations,
        maximum_anchor_distance_ratio=qty.maximum_anchor_distance_ratio,
    )

    add_fields: list[AdditionalFieldRule] = []
    seen_add_keys: set[str] = set()
    seen_add_priorities: set[int] = set()
    for idx, item in enumerate(raw.get("additional_fields") or []):
        path = f"additional_fields[{idx}]"
        if not isinstance(item, dict):
            raise ExtractionProfileConfigurationError(
                "INVALID_ADDITIONAL_FIELD",
                f"{path}: entry must be an object",
            )
        fk = str(item.get("field_key") or "").strip().lower()
        if not fk:
            raise ExtractionProfileConfigurationError(
                "INVALID_ADDITIONAL_FIELD",
                f"{path}.field_key is required",
            )
        if fk in seen_add_keys:
            raise ExtractionProfileConfigurationError(
                "DUPLICATE_ADDITIONAL_FIELD",
                f"{path}.field_key duplicate {fk!r}",
            )
        priority = int(item.get("priority") or 100)
        if priority in seen_add_priorities:
            raise ExtractionProfileConfigurationError(
                "DUPLICATE_PRIORITY",
                f"{path}.priority duplicate {priority}",
            )
        seen_add_keys.add(fk)
        seen_add_priorities.add(priority)
        if item.get("validation_rule"):
            _reject_custom_regex(
                str(item.get("validation_rule")),
                field=f"{path}.validation_rule",
            )
        add_fields.append(
            AdditionalFieldRule(
                field_key=fk,
                display_name=str(item.get("display_name") or fk).strip() or fk,
                aliases=_as_str_tuple(item.get("aliases"), field=f"{path}.aliases"),
                data_type=_parse_data_type(item.get("data_type"), field=f"{path}.data_type"),
                required=bool(item.get("required", False)),
                priority=priority,
                normalization_rule=(
                    str(item["normalization_rule"]).strip()
                    if item.get("normalization_rule")
                    else None
                ),
                validation_rule=None,
            )
        )

    vraw: dict[str, Any] = (
        raw["validation_rules"] if isinstance(raw.get("validation_rules"), dict) else {}
    )
    craw: dict[str, Any] = vraw["code"] if isinstance(vraw.get("code"), dict) else {}
    eraw: dict[str, Any] = vraw["ean"] if isinstance(vraw.get("ean"), dict) else {}
    validation = ExtractionValidationRules(
        code=CodeValidationRules(
            min_length=int(craw.get("min_length") or 1),
            max_length=int(craw.get("max_length") or 128),
            exact_length=(
                int(craw["exact_length"]) if craw.get("exact_length") is not None else None
            ),
            allow_letters=bool(craw.get("allow_letters", True)),
            allow_digits=bool(craw.get("allow_digits", True)),
            allow_hyphen=bool(craw.get("allow_hyphen", True)),
            allow_slash=bool(craw.get("allow_slash", True)),
            allow_spaces=bool(craw.get("allow_spaces", False)),
            preserve_leading_zeros=bool(craw.get("preserve_leading_zeros", True)),
            regex=None,
            reject_measurement_patterns=bool(
                craw.get("reject_measurement_patterns", True)
            ),
        ),
        ean=EanValidationRules(
            allow_ean8=bool(eraw.get("allow_ean8", True)),
            allow_ean12=bool(eraw.get("allow_ean12", True)),
            allow_ean13=bool(eraw.get("allow_ean13", True)),
            allow_ean14=bool(eraw.get("allow_ean14", True)),
            validate_checksum=bool(eraw.get("validate_checksum", True)),
        ),
        quantity_integer_only=True,
    )
    if craw.get("regex"):
        _reject_custom_regex(str(craw.get("regex")), field="validation_rules.code.regex")
    if validation.code.exact_length is not None:
        if validation.code.exact_length < 1 or validation.code.exact_length > 128:
            raise ExtractionProfileConfigurationError(
                "INVALID_CODE_LENGTH",
                "validation_rules.code.exact_length must be between 1 and 128",
            )

    label_raw: dict[str, Any] = (
        raw["label_detection_rules"]
        if isinstance(raw.get("label_detection_rules"), dict)
        else {}
    )
    label_detection = _parse_label_detection_rules(label_raw)

    formats = tuple(
        str(x).strip().upper()
        for x in (raw.get("accepted_barcode_formats") or [])
        if str(x).strip()
    ) or ExtractionProfileConfiguration().accepted_barcode_formats
    for fmt in formats:
        if fmt not in SUPPORTED_BARCODE_FORMATS:
            raise ExtractionProfileConfigurationError(
                "UNSUPPORTED_BARCODE_FORMAT", f"unsupported barcode format {fmt!r}"
            )

    payload_formats = tuple(
        str(x).strip().upper()
        for x in (raw.get("qr_payload_formats") or [])
        if str(x).strip()
    ) or ExtractionProfileConfiguration().qr_payload_formats

    aliases_raw: dict[str, Any] = (
        raw["aliases"] if isinstance(raw.get("aliases"), dict) else {}
    )
    aliases: dict[str, tuple[str, ...]] = {}
    for k, v in aliases_raw.items():
        aliases[str(k).strip().lower()] = _as_str_tuple(v, field=f"aliases.{k}")

    required = tuple(
        str(x).strip().lower()
        for x in (raw.get("required_fields") or ["internal_code", "quantity"])
        if str(x).strip()
    )

    custom_pattern = None
    if raw.get("custom_payload_pattern"):
        _reject_custom_regex(
            str(raw.get("custom_payload_pattern")),
            field="custom_payload_pattern",
        )

    allow_fallback = bool(raw.get("allow_unconfigured_code_source_fallback", False))

    if not sources_sorted:
        return default_extraction_configuration()

    return ExtractionProfileConfiguration(
        internal_code_sources=sources_sorted,
        forbidden_internal_code_sources=forbidden,
        quantity_rules=qty,
        additional_fields=tuple(add_fields),
        validation_rules=validation,
        label_detection_rules=label_detection,
        accepted_barcode_formats=formats,
        qr_payload_formats=payload_formats,
        custom_payload_pattern=custom_pattern,
        required_fields=required or ("internal_code", "quantity"),
        aliases=aliases,
        allow_unconfigured_code_source_fallback=allow_fallback,
    )


def _parse_quantity_presence(raw: object) -> QuantityPresence:
    key = str(raw or QuantityPresence.ALWAYS.value).strip().upper()
    try:
        return QuantityPresence(key)
    except ValueError as exc:
        raise ExtractionProfileConfigurationError(
            "INVALID_QUANTITY_PRESENCE",
            f"quantity_rules.expected_presence unsupported: {key!r}",
        ) from exc


def _parse_missing_quantity_action(raw: object) -> MissingQuantityAction:
    key = str(raw or MissingQuantityAction.PENDING_MANUAL_REVIEW.value).strip().upper()
    try:
        action = MissingQuantityAction(key)
    except ValueError as exc:
        raise ExtractionProfileConfigurationError(
            "INVALID_MISSING_QUANTITY_ACTION",
            f"quantity_rules.missing_quantity_action unsupported: {key!r}",
        ) from exc
    if action is MissingQuantityAction.RESOLVE_CODE_ONLY:
        raise ExtractionProfileConfigurationError(
            "RESOLVE_CODE_ONLY_NOT_SUPPORTED",
            "RESOLVE_CODE_ONLY is not enabled for automatic resolution in this phase",
        )
    return action


def _parse_label_detection_rules(raw: dict[str, Any]) -> LabelDetectionRules:
    defaults = LabelDetectionRules()
    if not raw:
        return defaults

    def _enum(cls, value: object, *, field: str, default):
        if value is None:
            return default
        key = str(value).strip().upper()
        try:
            return cls(key)
        except ValueError as exc:
            raise ExtractionProfileConfigurationError(
                "INVALID_LABEL_DETECTION",
                f"label_detection_rules.{field} unsupported: {key!r}",
            ) from exc

    min_area = float(
        raw["minimum_relative_area"]
        if raw.get("minimum_relative_area") is not None
        else defaults.minimum_relative_area
    )
    max_area = float(
        raw["maximum_relative_area"]
        if raw.get("maximum_relative_area") is not None
        else defaults.maximum_relative_area
    )
    if min_area < 0 or max_area > 1 or min_area > max_area:
        raise ExtractionProfileConfigurationError(
            "INVALID_LABEL_DETECTION",
            "label_detection_rules relative area bounds must satisfy 0 <= min <= max <= 1",
        )
    max_regions = int(
        raw["maximum_candidate_regions"]
        if raw.get("maximum_candidate_regions") is not None
        else defaults.maximum_candidate_regions
    )
    if max_regions < 1 or max_regions > 20:
        raise ExtractionProfileConfigurationError(
            "INVALID_LABEL_DETECTION",
            "label_detection_rules.maximum_candidate_regions must be 1..20",
        )
    min_anchors = int(
        raw["minimum_anchor_matches"]
        if raw.get("minimum_anchor_matches") is not None
        else defaults.minimum_anchor_matches
    )
    # Deskew flag: prefer allow_deskew; legacy allow_perspective_correction maps to deskew.
    if "allow_deskew" in raw:
        allow_deskew = bool(raw.get("allow_deskew"))
    elif "allow_perspective_correction" in raw:
        allow_deskew = bool(raw.get("allow_perspective_correction"))
    else:
        allow_deskew = defaults.allow_deskew

    policy = _enum(
        AnchorMatchPolicy,
        raw.get("anchor_match_policy"),
        field="anchor_match_policy",
        default=defaults.anchor_match_policy,
    )
    # If anchors are required via minimum_anchor_matches but policy omitted, upgrade.
    if min_anchors > 0 and raw.get("anchor_match_policy") is None:
        policy = AnchorMatchPolicy.ANCHORS_REQUIRED

    return LabelDetectionRules(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        expected_background=_enum(
            LabelBackgroundHint,
            raw.get("expected_background"),
            field="expected_background",
            default=defaults.expected_background,
        ),
        expected_shape=_enum(
            LabelShapeHint,
            raw.get("expected_shape"),
            field="expected_shape",
            default=defaults.expected_shape,
        ),
        expected_orientation=_enum(
            LabelOrientationHint,
            raw.get("expected_orientation"),
            field="expected_orientation",
            default=defaults.expected_orientation,
        ),
        primary_anchors=_as_str_tuple(
            raw.get("primary_anchors"), field="label_detection_rules.primary_anchors"
        )
        or defaults.primary_anchors,
        secondary_anchors=_as_str_tuple(
            raw.get("secondary_anchors"), field="label_detection_rules.secondary_anchors"
        )
        or defaults.secondary_anchors,
        minimum_anchor_matches=min_anchors,
        anchor_match_policy=policy,
        minimum_relative_area=min_area,
        maximum_relative_area=max_area,
        allow_rotation=bool(raw.get("allow_rotation", defaults.allow_rotation)),
        allow_deskew=allow_deskew,
        allow_perspective_correction=allow_deskew,
        allow_full_image_fallback=bool(
            raw.get("allow_full_image_fallback", defaults.allow_full_image_fallback)
        ),
        maximum_candidate_regions=max_regions,
    )


__all__ = [
    "ExtractionProfileConfigurationError",
    "parse_extraction_configuration",
]
