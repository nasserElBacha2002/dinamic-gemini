"""Phase 2 — LabelValidationService: single deterministic validation authority."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from re import Pattern

try:
    from re import _parser as sre_parse  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    import sre_parse  # type: ignore[no-redef]

from src.application.services.position_label_detection.payload_parser import (
    ParsedPositionLabelPayload,
    PositionLabelPayloadParser,
)
from src.domain.client_supplier.extraction_profile import (
    ExtractionProfileConfiguration,
    QrPayloadFormat,
)
from src.domain.label_profiles.entities import ResolvedLabelProfile
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource
from src.domain.label_validation import (
    CandidateLabel,
    LabelValidationErrorCode,
    LabelValidationResult,
    LabelValidationStatus,
    NormalizedItemLabel,
    NormalizedPositionLabel,
)
from src.domain.label_validation.context import LabelValidationContext
from src.domain.position_label_detection.entities import PositionLabelDetectionStatus
from src.domain.product_labels.format import (
    ProductLabelValidationStatus,
    parse_product_label_payload,
)

_DEFAULT_POSITION_MAX_PAYLOAD_BYTES = 8192
_NOT_OUR_POSITION_STATUSES = frozenset(
    {
        PositionLabelDetectionStatus.INVALID_JSON,
        PositionLabelDetectionStatus.INVALID_TYPE,
    }
)

logger = logging.getLogger(__name__)

_D1_PREFIX = re.compile(r"^D1\|", re.IGNORECASE)
_DINAMIC_POSITION_HINT = re.compile(r"DINAMIC_POSITION|\"type\"\s*:\s*\"DINAMIC", re.IGNORECASE)

_MAX_PAYLOAD_FOR_REGEX = 512
_COMPILED_PATTERN_CACHE_SIZE = 256

# Re-export for callers that imported context from this module.
__all__ = [
    "LabelProfileConfigurationError",
    "LabelValidationContext",
    "LabelValidationService",
    "compile_payload_pattern",
    "validate_extraction_configuration_for_code_scan",
]


class LabelProfileConfigurationError(ValueError):
    """Raised when supplier validation rules are malformed (config-time / load-time)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _pattern_has_unsafe_nested_quantifiers(pattern: str) -> bool:
    """Reject nested/ambiguous quantified constructs that enable classic ReDoS.

    Structural policy (Option A): disallow a quantified subpattern that itself
    contains another quantifier or alternation (``|``). Keeps simple char-class
    and literal quantifiers (``^[A-Z]{3}[0-9]+$``) valid.
    """
    try:
        tree = sre_parse.parse(pattern)
    except re.error:
        return False

    def walk(ops: sre_parse.SubPattern, *, inside_quantified: bool) -> bool:
        for op, av in ops:
            if op in (sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT):
                _min_r, _max_r, sub = av
                if inside_quantified:
                    return True
                if walk(sub, inside_quantified=True):
                    return True
            elif op is sre_parse.SUBPATTERN:
                sub = av[-1]
                if walk(sub, inside_quantified=inside_quantified):
                    return True
            elif op is sre_parse.BRANCH:
                if inside_quantified:
                    return True
                for branch in av[1]:
                    if walk(branch, inside_quantified=inside_quantified):
                        return True
            elif op is sre_parse.GROUPREF_EXISTS:
                # Conditional / advanced constructs — reject under quantified parents.
                if inside_quantified:
                    return True
                yes = av[1]
                no = av[2] if len(av) > 2 else None
                if walk(yes, inside_quantified=inside_quantified):
                    return True
                if no is not None and walk(no, inside_quantified=inside_quantified):
                    return True
            elif op is sre_parse.ASSERT or op is sre_parse.ASSERT_NOT:
                sub = av[1]
                if walk(sub, inside_quantified=inside_quantified):
                    return True
        return False

    return walk(tree, inside_quantified=False)


@lru_cache(maxsize=_COMPILED_PATTERN_CACHE_SIZE)
def compile_payload_pattern(pattern: str) -> Pattern[str]:
    """Compile and cache a supplier payload regex; reject unsafe/invalid patterns.

    Cache is bounded (``lru_cache``) and thread-safe under CPython GIL for
    cache bookkeeping. Pattern length and payload length remain additional limits.
    """
    text = (pattern or "").strip()
    if not text:
        raise LabelProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern must not be empty",
        )
    if len(text) > 200:
        raise LabelProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern exceeds 200 characters",
        )
    if _pattern_has_unsafe_nested_quantifiers(text):
        raise LabelProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            "custom_payload_pattern has nested quantifiers or quantified alternation",
        )
    try:
        return re.compile(text)
    except re.error as exc:
        raise LabelProfileConfigurationError(
            LabelValidationErrorCode.LABEL_PROFILE_CONFIGURATION_INVALID.value,
            f"invalid custom_payload_pattern: {exc}",
        ) from exc


def validate_extraction_configuration_for_code_scan(
    configuration: ExtractionProfileConfiguration,
) -> None:
    """Fail early when activating/writing a SUPPLIER profile used by CODE_SCAN."""
    if configuration.custom_payload_pattern:
        compile_payload_pattern(configuration.custom_payload_pattern)
    code_regex = configuration.validation_rules.code.regex
    if code_regex:
        compile_payload_pattern(code_regex)


class LabelValidationService:
    """Central deterministic validation entry point."""

    def __init__(
        self,
        *,
        position_parser: PositionLabelPayloadParser | None = None,
    ) -> None:
        self._position_parser = position_parser or PositionLabelPayloadParser(
            max_payload_bytes=_DEFAULT_POSITION_MAX_PAYLOAD_BYTES
        )

    def validate(
        self,
        candidate: CandidateLabel,
        *,
        context: LabelValidationContext,
        label_kind: LabelKind,
    ) -> LabelValidationResult:
        profile = self._profile_for(context, label_kind)
        source = profile.source if profile else LabelProfileSource.DINAMIC

        logger.info(
            "label_validation.start job_id=%s label_kind=%s profile_source=%s "
            "recognition_source=%s symbology=%s",
            context.job_id,
            label_kind.value,
            source.value,
            candidate.recognition_source.value,
            candidate.symbology,
        )

        if source is LabelProfileSource.SUPPLIER:
            dinamic_probe = self._probe_dinamic_integrity(candidate, label_kind)
            if dinamic_probe is not None:
                return dinamic_probe

        if source is LabelProfileSource.DINAMIC:
            result = self._validate_dinamic(candidate, label_kind=label_kind)
        else:
            result = self._validate_supplier(
                candidate,
                label_kind=label_kind,
                context=context,
                profile=profile,
            )

        logger.info(
            "label_validation.result job_id=%s label_kind=%s profile_source=%s "
            "status=%s error_code=%s",
            context.job_id,
            label_kind.value,
            source.value,
            result.status.value,
            result.error_code,
        )
        return result

    def validate_best_effort(
        self,
        candidate: CandidateLabel,
        *,
        context: LabelValidationContext,
    ) -> LabelValidationResult:
        """Evaluate ITEM and POSITION profiles; surface AMBIGUOUS when both VALID.

        Ignores ``label_kind_hint`` so CODE_SCAN cannot get accidental kind precedence.
        """
        item = self.validate(candidate, context=context, label_kind=LabelKind.ITEM)
        position = self.validate(candidate, context=context, label_kind=LabelKind.POSITION)
        if (
            item.status is LabelValidationStatus.VALID
            and position.status is LabelValidationStatus.VALID
        ):
            return LabelValidationResult(
                status=LabelValidationStatus.AMBIGUOUS,
                error_code=LabelValidationErrorCode.AMBIGUOUS_LABEL_KIND.value,
                detail="payload matches both ITEM and POSITION profiles",
                diagnostics={"item": item.diagnostics, "position": position.diagnostics},
            )
        if item.status is LabelValidationStatus.VALID:
            return item
        if position.status is LabelValidationStatus.VALID:
            return position
        # Prefer fail-closed Dinamic INVALID over soft NOT_APPLICABLE.
        if item.status is LabelValidationStatus.INVALID:
            return item
        if position.status is LabelValidationStatus.INVALID:
            return position
        return item if item.status is not LabelValidationStatus.NOT_APPLICABLE else position

    def _profile_for(
        self, context: LabelValidationContext, label_kind: LabelKind
    ) -> ResolvedLabelProfile | None:
        if context.resolved_profiles is None:
            return None
        return (
            context.resolved_profiles.item
            if label_kind is LabelKind.ITEM
            else context.resolved_profiles.position
        )

    def _probe_dinamic_integrity(
        self, candidate: CandidateLabel, label_kind: LabelKind
    ) -> LabelValidationResult | None:
        raw = (candidate.raw_payload or "").strip()
        if label_kind is LabelKind.ITEM and _D1_PREFIX.match(raw):
            parsed = parse_product_label_payload(raw)
            if parsed.status is ProductLabelValidationStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
                    detail=(
                        "valid Dinamic D1 payload rejected under SUPPLIER ITEM profile "
                        "(source mismatch; not a format error)"
                    ),
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                )
            if parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT:
                return None
            return LabelValidationResult.invalid(
                error_code=(
                    LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value
                    if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED
                    else LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value
                ),
                detail=parsed.detail or parsed.status.value,
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.ITEM,
                diagnostics={"product_label_status": parsed.status.value},
            )
        if label_kind is LabelKind.POSITION and _DINAMIC_POSITION_HINT.search(raw):
            parsed_pos = self._position_parser.parse(raw)
            if parsed_pos.status is PositionLabelDetectionStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_PROFILE_SOURCE_MISMATCH.value,
                    detail=(
                        "valid Dinamic POSITION payload rejected under SUPPLIER POSITION "
                        "profile (source mismatch; not a format error)"
                    ),
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.POSITION,
                )
            if parsed_pos.status not in _NOT_OUR_POSITION_STATUSES:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
                    detail=parsed_pos.detail or parsed_pos.status.value,
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.POSITION,
                )
        return None

    def _validate_dinamic(
        self, candidate: CandidateLabel, *, label_kind: LabelKind
    ) -> LabelValidationResult:
        raw = (candidate.raw_payload or "").strip()
        if label_kind is LabelKind.ITEM:
            parsed = parse_product_label_payload(raw)
            if parsed.status is ProductLabelValidationStatus.NOT_OUR_FORMAT:
                return LabelValidationResult.not_applicable(
                    detail="not Dinamic D1 format",
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.ITEM,
                )
            if parsed.status is not ProductLabelValidationStatus.VALID:
                return LabelValidationResult.invalid(
                    error_code=(
                        LabelValidationErrorCode.DINAMIC_CHECKSUM_FAILED.value
                        if parsed.status is ProductLabelValidationStatus.CHECKSUM_FAILED
                        else LabelValidationErrorCode.DINAMIC_FORMAT_INVALID.value
                    ),
                    detail=parsed.detail or parsed.status.value,
                    profile_source=LabelProfileSource.DINAMIC,
                    label_kind=LabelKind.ITEM,
                    diagnostics={"product_label_status": parsed.status.value},
                )
            assert parsed.internal_code is not None
            return LabelValidationResult.valid(
                NormalizedItemLabel(
                    label_id=parsed.label_id,
                    sku=parsed.internal_code,
                    quantity=parsed.quantity,
                    raw_payload=parsed.normalized_payload or raw,
                    profile_source=LabelProfileSource.DINAMIC,
                    format_version=parsed.format_version,
                    symbology=candidate.symbology,
                    checksum_ok=True,
                ),
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.ITEM,
            )

        parsed_pos = self._position_parser.parse(raw)
        return self._dinamic_position_result(parsed_pos, candidate=candidate, raw=raw)

    def _dinamic_position_result(
        self,
        parsed_pos: ParsedPositionLabelPayload,
        *,
        candidate: CandidateLabel,
        raw: str,
    ) -> LabelValidationResult:
        if parsed_pos.status in _NOT_OUR_POSITION_STATUSES:
            return LabelValidationResult.not_applicable(
                detail=parsed_pos.detail or "not Dinamic POSITION format",
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.POSITION,
            )
        if parsed_pos.status is not PositionLabelDetectionStatus.VALID:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.DINAMIC_POSITION_INVALID.value,
                detail=parsed_pos.detail or parsed_pos.status.value,
                profile_source=LabelProfileSource.DINAMIC,
                label_kind=LabelKind.POSITION,
                diagnostics={"position_status": parsed_pos.status.value},
            )
        position_id = (parsed_pos.label_id or "").strip()
        payload = parsed_pos.payload or {}
        return LabelValidationResult.valid(
            NormalizedPositionLabel(
                position_id=position_id,
                pallet=str(payload["pallet"]).strip() if payload.get("pallet") else None,
                side=str(payload["side"]).strip() if payload.get("side") else None,
                level=str(payload["level"]).strip() if payload.get("level") else None,
                raw_payload=raw,
                profile_source=LabelProfileSource.DINAMIC,
                symbology=candidate.symbology,
            ),
            profile_source=LabelProfileSource.DINAMIC,
            label_kind=LabelKind.POSITION,
        )

    def _validate_supplier(
        self,
        candidate: CandidateLabel,
        *,
        label_kind: LabelKind,
        context: LabelValidationContext,
        profile: ResolvedLabelProfile | None,
    ) -> LabelValidationResult:
        del profile  # used for logging at call site; config comes from snapshot
        config = (
            context.item_extraction_configuration
            if label_kind is LabelKind.ITEM
            else context.position_extraction_configuration
        )
        if config is None:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED.value,
                detail="supplier extraction configuration missing from job snapshot",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        raw = (candidate.raw_payload or "").strip()
        if len(raw) > _MAX_PAYLOAD_FOR_REGEX:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail="payload exceeds validation length limit",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        if not self._symbology_accepted(candidate.symbology, config):
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_SYMBOLOGY_REJECTED.value,
                detail=f"symbology {candidate.symbology!r} not in accepted_barcode_formats",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        try:
            pattern_text = config.custom_payload_pattern or config.validation_rules.code.regex
            if pattern_text:
                compiled = compile_payload_pattern(pattern_text)
                if not compiled.fullmatch(raw):
                    return LabelValidationResult.invalid(
                        error_code=LabelValidationErrorCode.LABEL_PATTERN_MISMATCH.value,
                        detail="payload does not match custom_payload_pattern",
                        profile_source=LabelProfileSource.SUPPLIER,
                        label_kind=label_kind,
                    )
            else:
                code_err = self._validate_code_rules(raw, config, label_kind=label_kind)
                if code_err is not None:
                    return code_err
        except LabelProfileConfigurationError as exc:
            return LabelValidationResult(
                status=LabelValidationStatus.TECHNICAL_ERROR,
                error_code=exc.code,
                detail=exc.message,
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )

        if label_kind is LabelKind.ITEM:
            return self._normalize_supplier_item(candidate, raw=raw, config=config)
        return self._normalize_supplier_position(candidate, raw=raw, config=config)

    def _extract_supplier_item_fields(
        self,
        candidate: CandidateLabel,
        *,
        raw: str,
        config: ExtractionProfileConfiguration,
    ) -> tuple[str, str | None, int | float | None]:
        """Declarative whole-payload / CODE_QUANTITY_PIPE extraction only (Phase 2).

        Named-capture / delimiter / fixed-segment mapping is deferred to a later phase.
        Never invents quantity=1.
        """
        sku = (candidate.sku or "").strip() or None
        label_id = (candidate.label_id or "").strip() or None
        quantity = candidate.quantity
        formats = {str(f).strip().upper() for f in (config.qr_payload_formats or ())}
        if (
            QrPayloadFormat.CODE_QUANTITY_PIPE.value in formats
            and "|" in raw
            and quantity is None
        ):
            code_part, _, qty_part = raw.partition("|")
            code_part = code_part.strip()
            qty_part = qty_part.strip()
            if code_part and qty_part.isdigit():
                sku = sku or code_part
                label_id = label_id or code_part
                quantity = int(qty_part)
        if not sku:
            sku = raw
        if not label_id:
            label_id = raw
        return sku, label_id, quantity

    def _normalize_supplier_item(
        self,
        candidate: CandidateLabel,
        *,
        raw: str,
        config: ExtractionProfileConfiguration,
    ) -> LabelValidationResult:
        sku, label_id, quantity = self._extract_supplier_item_fields(
            candidate, raw=raw, config=config
        )
        required = {f.strip().lower() for f in config.required_fields}
        if "internal_code" in required and not sku:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="internal_code/sku required",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        if "quantity" in required and quantity is None:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="quantity required by supplier profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.ITEM,
            )
        qty_out: int | None = None
        if quantity is not None:
            try:
                qty_out = int(quantity)
            except (TypeError, ValueError):
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity must be an integer",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                )
            if qty_out < 1 and not config.quantity_rules.allow_negative:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="quantity must be a positive integer",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=LabelKind.ITEM,
                )
        return LabelValidationResult.valid(
            NormalizedItemLabel(
                label_id=label_id,
                sku=sku,
                quantity=qty_out,
                raw_payload=raw,
                profile_source=LabelProfileSource.SUPPLIER,
                symbology=candidate.symbology,
            ),
            profile_source=LabelProfileSource.SUPPLIER,
            label_kind=LabelKind.ITEM,
        )

    def _normalize_supplier_position(
        self,
        candidate: CandidateLabel,
        *,
        raw: str,
        config: ExtractionProfileConfiguration,
    ) -> LabelValidationResult:
        # Phase 2: whole payload as position_id unless candidate already carries fields.
        # Structured barcode field mapping (named capture / delimiter) is deferred.
        position_id = (candidate.position_id or candidate.label_id or raw).strip()
        pallet = (candidate.pallet or "").strip() or None
        side = (candidate.side or "").strip() or None
        level = (candidate.level or "").strip() or None
        if not position_id:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="position_id required",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        required = {f.strip().lower() for f in config.required_fields}
        if "pallet" in required and not pallet:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="pallet required by supplier POSITION profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        if "side" in required and not side:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_REQUIRED_FIELD_MISSING.value,
                detail="side required by supplier POSITION profile",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=LabelKind.POSITION,
            )
        return LabelValidationResult.valid(
            NormalizedPositionLabel(
                position_id=position_id,
                pallet=pallet,
                side=side,
                level=level,
                raw_payload=raw,
                profile_source=LabelProfileSource.SUPPLIER,
                symbology=candidate.symbology,
            ),
            profile_source=LabelProfileSource.SUPPLIER,
            label_kind=LabelKind.POSITION,
        )

    @staticmethod
    def _symbology_accepted(
        symbology: str | None, config: ExtractionProfileConfiguration
    ) -> bool:
        if not config.accepted_barcode_formats:
            return True
        if not symbology:
            return False
        accepted = {s.strip().upper() for s in config.accepted_barcode_formats}
        sym = symbology.strip().upper().replace("-", "_")
        aliases = {
            "QR_CODE": "QR",
            "QRCODE": "QR",
            "CODE_128": "CODE128",
            "CODE128": "CODE128",
            "EAN_13": "EAN13",
            "EAN_8": "EAN8",
            "UPC_A": "UPC_A",
            "UPCA": "UPC_A",
        }
        normalized = aliases.get(sym, sym)
        return normalized in accepted or sym in accepted

    def _validate_code_rules(
        self,
        raw: str,
        config: ExtractionProfileConfiguration,
        *,
        label_kind: LabelKind,
    ) -> LabelValidationResult | None:
        rules = config.validation_rules.code
        length = len(raw)
        if rules.exact_length is not None and length != rules.exact_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code length must be exactly {rules.exact_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        if rules.min_length is not None and length < rules.min_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code shorter than min_length {rules.min_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        if rules.max_length is not None and length > rules.max_length:
            return LabelValidationResult.invalid(
                error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                detail=f"code longer than max_length {rules.max_length}",
                profile_source=LabelProfileSource.SUPPLIER,
                label_kind=label_kind,
            )
        for ch in raw:
            if ch.isalpha() and not rules.allow_letters:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="letters not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch.isdigit() and not rules.allow_digits:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="digits not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch == "-" and not rules.allow_hyphen:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="hyphen not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch == "/" and not rules.allow_slash:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="slash not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
            if ch.isspace() and not rules.allow_spaces:
                return LabelValidationResult.invalid(
                    error_code=LabelValidationErrorCode.LABEL_FIELD_INVALID.value,
                    detail="spaces not allowed in code",
                    profile_source=LabelProfileSource.SUPPLIER,
                    label_kind=label_kind,
                )
        return None
