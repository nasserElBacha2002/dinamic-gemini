"""Parse / serialize ExtractionProfileConfiguration JSON (Phase 6)."""

from __future__ import annotations

import re
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
    QuantityExtractionRules,
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


def _validate_optional_regex(pattern: str | None) -> str | None:
    if pattern is None:
        return None
    text = pattern.strip()
    if not text:
        return None
    if len(text) > _MAX_REGEX_LEN:
        raise ExtractionProfileConfigurationError(
            "REGEX_TOO_LONG", f"regex exceeds {_MAX_REGEX_LEN} chars"
        )
    # Reject nested quantifiers / catastrophic backtracking heuristics (basic).
    if "(?=" in text or "(?!" in text or "(?<=" in text or "(?<!" in text:
        raise ExtractionProfileConfigurationError(
            "REGEX_UNSAFE", "lookaround assertions are not allowed"
        )
    try:
        re.compile(text)
    except re.error as exc:
        raise ExtractionProfileConfigurationError(
            "REGEX_INVALID", f"invalid regex: {exc}"
        ) from exc
    return text


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
        pattern = _validate_optional_regex(
            str(item["pattern"]).strip() if item.get("pattern") else None
        )
        sources.append(
            InternalCodeSourceRule(
                field_key=key,
                priority=priority,
                enabled=bool(item.get("enabled", True)),
                allowed_as_internal_code=bool(item.get("allowed_as_internal_code", True)),
                requires_label=bool(item.get("requires_label", False)),
                pattern=pattern,
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

    add_fields: list[AdditionalFieldRule] = []
    for item in raw.get("additional_fields") or []:
        if not isinstance(item, dict):
            continue
        fk = str(item.get("field_key") or "").strip().lower()
        if not fk:
            raise ExtractionProfileConfigurationError(
                "INVALID_ADDITIONAL_FIELD", "additional field_key is required"
            )
        add_fields.append(
            AdditionalFieldRule(
                field_key=fk,
                display_name=str(item.get("display_name") or fk).strip() or fk,
                aliases=_as_str_tuple(item.get("aliases"), field=f"additional.{fk}.aliases"),
                data_type=_parse_data_type(item.get("data_type"), field=fk),
                required=bool(item.get("required", False)),
                priority=int(item.get("priority") or 100),
                normalization_rule=(
                    str(item["normalization_rule"]).strip()
                    if item.get("normalization_rule")
                    else None
                ),
                validation_rule=_validate_optional_regex(
                    str(item["validation_rule"]).strip()
                    if item.get("validation_rule")
                    else None
                ),
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
            allow_letters=bool(craw.get("allow_letters", True)),
            allow_digits=bool(craw.get("allow_digits", True)),
            allow_hyphen=bool(craw.get("allow_hyphen", True)),
            allow_slash=bool(craw.get("allow_slash", True)),
            allow_spaces=bool(craw.get("allow_spaces", False)),
            preserve_leading_zeros=bool(craw.get("preserve_leading_zeros", True)),
            regex=_validate_optional_regex(
                str(craw["regex"]).strip() if craw.get("regex") else None
            ),
        ),
        ean=EanValidationRules(
            allow_ean8=bool(eraw.get("allow_ean8", True)),
            allow_ean12=bool(eraw.get("allow_ean12", True)),
            allow_ean13=bool(eraw.get("allow_ean13", True)),
            allow_ean14=bool(eraw.get("allow_ean14", True)),
            validate_checksum=bool(eraw.get("validate_checksum", True)),
        ),
        quantity_integer_only=bool(vraw.get("quantity_integer_only", True)),
    )

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

    custom_pattern = _validate_optional_regex(
        str(raw["custom_payload_pattern"]).strip()
        if raw.get("custom_payload_pattern")
        else None
    )

    if not sources_sorted:
        return default_extraction_configuration()

    return ExtractionProfileConfiguration(
        internal_code_sources=sources_sorted,
        forbidden_internal_code_sources=forbidden,
        quantity_rules=qty,
        additional_fields=tuple(add_fields),
        validation_rules=validation,
        accepted_barcode_formats=formats,
        qr_payload_formats=payload_formats,
        custom_payload_pattern=custom_pattern,
        required_fields=required or ("internal_code", "quantity"),
        aliases=aliases,
    )


__all__ = [
    "ExtractionProfileConfigurationError",
    "parse_extraction_configuration",
]
