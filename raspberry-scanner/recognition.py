"""Local, deterministic recognition selected from the offline snapshot.

This intentionally implements only the code-scanner subset already exported by
``configuration_for_offline``: Dinamic D1 / DINAMIC_POSITION and supplier
deterministic SIMPLE or SEGMENTED profiles.  Unsupported supplier structures
are reported as unresolved; they are never treated as DINAMIC or accepted.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from typing import Any

from config.models import RecognitionProfile
from config.service import ConfigService


class SelectionError(ValueError):
    """The requested operational selection is not valid offline."""


@dataclass(frozen=True)
class Selection:
    client_id: str | None = None
    supplier_id: str | None = None


class RecognitionService:
    """Owns the ephemeral client/supplier selection and its read policy."""

    def __init__(self, config_service: ConfigService) -> None:
        self._config_service = config_service
        self._lock = threading.Lock()
        self._selection = Selection()

    def selection(self) -> dict[str, object]:
        with self._lock:
            selection = self._selection
        return self._policy_for_selection(selection)

    def select(
        self,
        client_id: object,
        supplier_id: object,
        *,
        scanning: bool,
    ) -> dict[str, object]:
        if scanning:
            raise SelectionError("selection_locked_while_scanning")
        if not isinstance(client_id, str) or not client_id.strip():
            raise SelectionError("client_id_required")
        if supplier_id is not None and (
            not isinstance(supplier_id, str) or not supplier_id.strip()
        ):
            raise SelectionError("supplier_id_must_be_string_or_null")

        normalized_client = client_id.strip()
        normalized_supplier = supplier_id.strip() if isinstance(supplier_id, str) else None
        snapshot = self._config_service.snapshot()
        if snapshot is None:
            raise SelectionError("offline_configuration_unavailable")
        client = snapshot.client(normalized_client)
        if client is None:
            raise SelectionError("client_not_found")
        if normalized_supplier is not None and client.supplier(normalized_supplier) is None:
            raise SelectionError("supplier_not_found_for_client")

        with self._lock:
            self._selection = Selection(normalized_client, normalized_supplier)
        return self._policy_for_selection(Selection(normalized_client, normalized_supplier))

    def process(self, raw_value: str) -> dict[str, object]:
        """Classify one raw serial value using the current offline selection."""
        with self._lock:
            selection = self._selection
        if selection.client_id is None or selection.supplier_id is None:
            return {"accepted": True, "classification": "RAW", "recognition": self._policy(selection)}

        snapshot = self._config_service.snapshot()
        client = snapshot.client(selection.client_id) if snapshot else None
        supplier = client.supplier(selection.supplier_id) if client else None
        # A snapshot replacement must not turn a formerly valid selection into
        # a cross-client/default policy.  Fail closed until the user reselects.
        if supplier is None or client is None:
            return {"accepted": False, "classification": "CONFIGURATION_INVALID", "recognition": self._policy(selection)}

        outcomes = {
            "ITEM": self._recognize_kind(raw_value, supplier.item_source, client.profile(supplier.client_supplier_id, "ITEM"), "ITEM"),
            "POSITION": self._recognize_kind(raw_value, supplier.position_source, client.profile(supplier.client_supplier_id, "POSITION"), "POSITION"),
        }
        accepted_kinds = [
            kind for kind, outcome in outcomes.items()
            if outcome["status"] == "VALID"
        ]
        ambiguous = (
            len(accepted_kinds) == 2
            and outcomes["ITEM"].get("source") == "SUPPLIER"
            and outcomes["POSITION"].get("source") == "SUPPLIER"
            and outcomes["ITEM"].get("normalized_payload")
            == outcomes["POSITION"].get("normalized_payload")
        )
        return {
            "accepted": bool(accepted_kinds),
            "classification": (
                accepted_kinds[0]
                if len(accepted_kinds) == 1
                else "AMBIGUOUS" if ambiguous else "REJECTED"
            ),
            "recognition": {**self._policy(selection, supplier.item_source, supplier.position_source), "results": outcomes},
        }

    def _policy_for_selection(self, selection: Selection) -> dict[str, object]:
        if selection.supplier_id is None:
            return self._policy(selection)
        snapshot = self._config_service.snapshot()
        client = snapshot.client(selection.client_id) if snapshot and selection.client_id else None
        supplier = client.supplier(selection.supplier_id) if client else None
        return self._policy(
            selection,
            supplier.item_source if supplier else None,
            supplier.position_source if supplier else None,
        )

    @staticmethod
    def _policy(selection: Selection, item_source: str | None = None, position_source: str | None = None) -> dict[str, object]:
        policy: dict[str, object] = {
            "selection_mode": "SPECIFIC" if selection.supplier_id else "ALL",
            "client_id": selection.client_id,
            "supplier_id": selection.supplier_id,
        }
        if selection.supplier_id:
            policy["item_source"] = item_source
            policy["position_source"] = position_source
        return policy

    def _recognize_kind(self, raw: str, source: str, profile: RecognitionProfile | None, kind: str) -> dict[str, object]:
        if source == "DINAMIC":
            return _dinamic(raw, kind)
        if profile is None:
            return {"status": "CONFIGURATION_INVALID", "source": "SUPPLIER"}
        # Mobile reserves D1-shaped ITEM values for the Dinamic consolidator;
        # supplier ITEM validation must not revive a failed D1 candidate.
        if kind == "ITEM":
            dinamic_item = _dinamic(raw, "ITEM")
            if (
                dinamic_item["status"] == "VALID"
                or (
                    dinamic_item["status"] == "INVALID"
                    and dinamic_item.get("error_code") != "UNKNOWN_VERSION"
                )
            ):
                return _not_applicable(profile, "DINAMIC_D1_RESERVED")
        return _supplier(raw, kind, profile)


_D1 = re.compile(r"^D1\|([0-9A-HJKMNP-TV-Z]{10})\|([^|\n]{1,48})\|([1-9]\d{0,7})\|([0-9A-Z])$", re.I)
_CHECKSUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _dinamic(raw: str, kind: str) -> dict[str, object]:
    text = raw.strip()
    if kind == "ITEM":
        match = _D1.fullmatch(text)
        if not match:
            if re.match(r"^D\d+\|", text, re.IGNORECASE):
                return {
                    "status": "INVALID",
                    "source": "DINAMIC",
                    "error_code": (
                        "UNKNOWN_VERSION"
                        if not text.upper().startswith("D1|")
                        else "D1_MALFORMED"
                    ),
                }
            return {"status": "NOT_APPLICABLE", "source": "DINAMIC"}
        label_id, internal_code, quantity, received = match.groups()
        body = f"D1|{label_id.upper()}|{internal_code.strip()}|{quantity}"
        total = sum(((_CHECKSUM.index(ch) if ch in _CHECKSUM else ord(ch) % 36) * (index + 1)) for index, ch in enumerate(body.upper())) % 36
        if received.upper() != _CHECKSUM[total]:
            return {"status": "INVALID", "source": "DINAMIC", "error_code": "D1_CHECKSUM_FAILED"}
        return {"status": "VALID", "source": "DINAMIC", "label_id": label_id.upper(), "internal_code": internal_code.strip(), "quantity": int(quantity)}
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {"status": "NOT_APPLICABLE", "source": "DINAMIC"}
    if not isinstance(value, dict) or value.get("type") != "DINAMIC_POSITION":
        return {"status": "NOT_APPLICABLE", "source": "DINAMIC"}
    label_id = value.get("label_id") or value.get("position_id")
    version = value.get("version", 1)
    if (
        not isinstance(label_id, str)
        or not label_id.strip()
        or type(version) is not int
        or version not in (1, 2)
    ):
        return {"status": "INVALID", "source": "DINAMIC", "error_code": "DINAMIC_POSITION_INVALID"}
    if version == 2 and (
        not isinstance(value.get("pallet"), str)
        or not value["pallet"].strip()
        or value.get("side") not in ("LEFT", "RIGHT")
        or not all(
            type(value.get(key)) is int and value[key] >= 1
            for key in ("level", "marker_index", "marker_total")
        )
        or value["marker_index"] > value["marker_total"]
    ):
        return {"status": "INVALID", "source": "DINAMIC", "error_code": "DINAMIC_POSITION_INVALID"}
    result: dict[str, object] = {
        "status": "VALID",
        "source": "DINAMIC",
        "position_id": label_id.strip(),
    }
    if version == 2:
        result.update(
            {
                "pallet": value["pallet"].strip(),
                "side": value["side"],
                "level": value["level"],
                "marker_index": value["marker_index"],
                "marker_total": value["marker_total"],
            }
        )
    return result


def _supplier(raw: str, kind: str, profile: RecognitionProfile) -> dict[str, object]:
    config = profile.configuration
    if profile.configuration_schema_version not in (1, 2):
        return _configuration_invalid(profile, "CONFIGURATION_SCHEMA_UNSUPPORTED")
    config_schema = config.get("configuration_schema_version")
    if config_schema is not None and config_schema != profile.configuration_schema_version:
        return _configuration_invalid(profile, "CONFIGURATION_SCHEMA_MISMATCH")
    rules = config.get("deterministic")
    if not isinstance(rules, dict):
        return _unresolved(profile, "DETERMINISTIC_RULES_REQUIRED")
    structure = str(rules.get("payload_structure", "SIMPLE")).upper()
    if structure == "GS1":
        return _unresolved(profile, "GS1_NOT_SUPPORTED_OFFLINE")
    if structure not in ("SIMPLE", "SEGMENTED"):
        return _unresolved(profile, "PAYLOAD_STRUCTURE_UNSUPPORTED")
    mappings_raw = rules.get("field_mappings", [])
    if not isinstance(mappings_raw, list):
        return _configuration_invalid(profile, "FIELD_MAPPINGS_INVALID")
    mappings = mappings_raw
    fields: dict[str, str] = {}
    if structure == "SEGMENTED":
        delimiter = rules.get("delimiter", "|")
        if not isinstance(delimiter, str) or not delimiter:
            return _configuration_invalid(profile, "DELIMITER_INVALID")
        structural = _normalize_structural(raw, rules)
        parts = structural.split(delimiter)
        expected = rules.get("expected_segment_count")
        if (
            expected is not None
            and (type(expected) is not int or expected < 1)
        ):
            return _configuration_invalid(profile, "SEGMENT_COUNT_INVALID")
        if (expected is not None and len(parts) != expected) or len(parts) > 32:
            return _not_applicable(profile, "LABEL_SEGMENT_COUNT_MISMATCH")
        for mapping in mappings:
            if not isinstance(mapping, dict):
                return _configuration_invalid(profile, "FIELD_MAPPING_INVALID")
            if str(mapping.get("source", "")).upper() != "SEGMENT":
                continue
            index = mapping.get("segment_index")
            target = str(mapping.get("target", "")).lower()
            if not isinstance(index, int) or index < 0 or index >= len(parts) or not target:
                return _not_applicable(profile, "LABEL_SEGMENT_COUNT_MISMATCH")
            value = _normalize_field(parts[index], rules)
            if target == "quantity":
                quantity_error = _quantity_error(value, config)
                if quantity_error:
                    return _invalid(profile, quantity_error)
            fields[target] = value
        structural_payload = structural
    else:
        structural_payload = _normalize_field(_normalize_structural(raw, rules), rules)
        for mapping in mappings:
            if not isinstance(mapping, dict):
                return _configuration_invalid(profile, "FIELD_MAPPING_INVALID")
            if str(mapping.get("source", "")).upper() == "WHOLE" and mapping.get("target"):
                target = str(mapping["target"]).lower()
                if target == "quantity":
                    quantity_error = _quantity_error(structural_payload, config)
                    if quantity_error:
                        return _invalid(profile, quantity_error)
                fields[target] = structural_payload
        if not mappings:
            fields["position_id" if kind == "POSITION" else "label_id"] = structural_payload
    identity = _identity(kind, structure, fields, structural_payload)
    if not identity:
        return _invalid(profile, "LABEL_REQUIRED_FIELD_MISSING")
    if not _shape_ok(identity, rules):
        return _not_applicable(profile, "LABEL_SHAPE_MISMATCH")
    required = {str(field).lower() for field in config.get("required_fields", []) if isinstance(field, str)}
    if kind == "POSITION" and not fields.get("position_id") and not fields.get("label_id"):
        return _invalid(profile, "LABEL_REQUIRED_FIELD_MISSING")
    if kind == "ITEM" and required and not all(fields.get(field) for field in required):
        return _invalid(profile, "LABEL_REQUIRED_FIELD_MISSING")
    return {
        "status": "VALID", "source": "SUPPLIER",
        "profile_id": profile.profile_id, "profile_version": profile.profile_version,
        "semantic_type": profile.semantic_type, "recognition_mode": profile.recognition_mode,
        "configuration_schema_version": profile.configuration_schema_version,
        "normalized_payload": structural_payload, "value": identity,
        "label_id": fields.get("label_id"),
        "sku": fields.get("sku") or fields.get("internal_code"),
        "quantity": fields.get("quantity"),
        "position_id": fields.get("position_id") or fields.get("label_id"),
        "pallet": fields.get("pallet"),
        "side": fields.get("side"),
    }


def _normalize_structural(value: str, rules: dict[str, Any]) -> str:
    normalization = rules.get("normalization") if isinstance(rules.get("normalization"), dict) else {}
    return value.strip() if normalization.get("trim_outer_whitespace", True) else value


def _normalize_field(value: str, rules: dict[str, Any]) -> str:
    normalization = rules.get("normalization") if isinstance(rules.get("normalization"), dict) else {}
    result = _normalize_structural(value, rules)
    if normalization.get("remove_internal_spaces"):
        result = re.sub(r"\s+", "", result)
    if normalization.get("remove_hyphens"):
        result = result.replace("-", "")
    case = str(normalization.get("case_normalization", "NONE")).upper()
    return result.upper() if case == "UPPER" else result.lower() if case == "LOWER" else result


def _identity(kind: str, structure: str, fields: dict[str, str], payload: str) -> str:
    if structure != "SEGMENTED":
        return payload
    if kind == "ITEM":
        return fields.get("label_id") or fields.get("sku") or ""
    return fields.get("position_id") or fields.get("label_id") or ""


def _shape_ok(value: str, rules: dict[str, Any]) -> bool:
    if rules.get("expected_prefix") and not value.startswith(str(rules["expected_prefix"]).strip()): return False
    if rules.get("expected_suffix") and not value.endswith(str(rules["expected_suffix"]).strip()): return False
    if isinstance(rules.get("exact_length"), int) and len(value) != rules["exact_length"]: return False
    if isinstance(rules.get("min_length"), int) and len(value) < rules["min_length"]: return False
    if isinstance(rules.get("max_length"), int) and len(value) > rules["max_length"]: return False
    charset = str(rules.get("character_set", "ANY")).upper()
    patterns = {"NUMERIC": r"\d+", "ALPHANUMERIC": r"[A-Za-z0-9]+", "UPPERCASE_ALPHANUMERIC": r"[A-Z0-9]+", "ALPHANUMERIC_WITH_HYPHEN": r"[A-Za-z0-9-]+", "HEX": r"[0-9a-fA-F]+"}
    return charset not in patterns or re.fullmatch(patterns[charset], value) is not None


def _quantity_error(value: str, config: dict[str, Any]) -> str | None:
    if not re.fullmatch(r"[1-9]\d*", value):
        return "LABEL_FIELD_INVALID"
    rules = config.get("quantity_rules")
    rules = rules if isinstance(rules, dict) else {}
    quantity = int(value)
    minimum = rules.get("minimum", 1)
    maximum = rules.get("maximum", 99_999_999)
    if (
        type(minimum) is not int
        or type(maximum) is not int
        or minimum < 1
        or maximum < minimum
    ):
        return "QUANTITY_RULES_INVALID"
    return None if minimum <= quantity <= maximum else "LABEL_FIELD_INVALID"


def _not_applicable(profile: RecognitionProfile, code: str) -> dict[str, object]:
    return {"status": "NOT_APPLICABLE", "source": "SUPPLIER", "profile_id": profile.profile_id, "error_code": code}


def _invalid(profile: RecognitionProfile, code: str) -> dict[str, object]:
    return {"status": "INVALID", "source": "SUPPLIER", "profile_id": profile.profile_id, "error_code": code}


def _configuration_invalid(profile: RecognitionProfile, code: str) -> dict[str, object]:
    return {"status": "CONFIGURATION_INVALID", "source": "SUPPLIER", "profile_id": profile.profile_id, "error_code": code}


def _unresolved(profile: RecognitionProfile, code: str) -> dict[str, object]:
    return {"status": "UNRESOLVED_OFFLINE", "source": "SUPPLIER", "profile_id": profile.profile_id, "error_code": code}
