"""Phase 5 — ExternalImageAnalysisProvider for single-label fallback (not hybrid aisle schema).

Critical contract: external fallback must NOT route through GeminiGlobalAnalyzer /
GlobalEntityResponseV21. That hybrid schema is for multi-entity aisle analysis and caused
incident a22bb927 (EXTERNAL_NO_RESULT): Gemini returned entities with nested codes while
the parser only read top-level ``internal_code`` / ``quantity``.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.application.ports.external_image_analysis_provider import (
    ExternalAnalysisContext,
    ExternalAnalysisResult,
    ExternalAnalysisStatus,
    ExternalImageInput,
)
from src.application.services.image_processing.external_cost_estimator import (
    ExternalCostEstimator,
)
from src.application.services.image_processing.external_fallback_prompt import (
    EXTERNAL_FALLBACK_PROMPT_VERSION,
    build_external_fallback_prompt,
)
from src.application.services.image_processing.external_fallback_schema_error import (
    build_external_schema_validation_error,
    response_trace_metadata,
)
from src.llm.errors import LLMProviderError
from src.llm.schema_versions import LlmSchemaVersion
from src.llm.types import LLMRequest
from src.pipeline.providers.registry import UnknownPipelineProviderError
from src.pipeline.services.pipeline_provider_resolver import resolve_llm_executor_for_context
from src.pipeline.services.provider_llm_request_metadata import (
    apply_job_model_name_to_llm_request_metadata,
)

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class ExternalFallbackLabelResponse(BaseModel):
    """Structured output schema matching ``EXTERNAL_FALLBACK_PROMPT_TEXT``."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="VALID | INVALID | AMBIGUOUS | NO_RESULT")
    internal_code: str | None = Field(None, description="Product / internal code or null")
    quantity: int | None = Field(None, description="Positive integer quantity or null")
    confidence: float | None = Field(None, description="Confidence in [0,1] or null")
    warnings: list[str] = Field(default_factory=list)
    reason: str | None = Field(None, description="Short reason when not VALID")


def _sanitize_message(message: str | None, *, limit: int = 500) -> str:
    text = (message or "").strip()
    for secret_marker in ("api_key", "apikey", "authorization", "bearer "):
        if secret_marker in text.lower():
            return "provider_error_redacted"
    return text[:limit]


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = _FENCE_RE.sub("", cleaned).strip()
    return cleaned


def _coerce_quantity(qty_raw: Any) -> int | None:
    if isinstance(qty_raw, bool):
        return None
    if isinstance(qty_raw, int):
        return qty_raw
    if isinstance(qty_raw, float) and qty_raw.is_integer():
        return int(qty_raw)
    if isinstance(qty_raw, str):
        digits = qty_raw.strip()
        if digits.isdigit():
            return int(digits)
    return None


def _extract_code(parsed: dict[str, Any]) -> str | None:
    for key in (
        "internal_code",
        "internalCode",
        "code",
        "sku",
        "codigo",
        "codigo_interno",
        "article",
        "ean",
    ):
        raw = parsed.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return str(int(raw)) if float(raw).is_integer() else str(raw)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _looks_like_hybrid_v21(parsed: dict[str, Any]) -> bool:
    return "entities" in parsed and "total_entities_detected" in parsed


def parse_external_fallback_payload(
    parsed: dict[str, Any] | None,
    *,
    raw_text: str | None = None,
) -> ExternalAnalysisResult:
    """Map provider JSON → ExternalAnalysisResult with specific error codes.

    ``EXTERNAL_NO_RESULT`` is reserved for an explicit provider NO_RESULT declaration
    after a successful parse — never for parse/schema failures.
    """
    meta: dict[str, Any] = {
        "parse_status": "ok",
        "response_present": bool(raw_text) or bool(parsed),
        "raw_text_len": len(raw_text or ""),
        "top_level_keys": sorted(parsed.keys())[:30] if isinstance(parsed, dict) else [],
    }

    if not parsed:
        if not (raw_text or "").strip():
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                error_code="EXTERNAL_EMPTY_RESPONSE",
                error_message="provider returned empty response body",
                additional_fields={**meta, "parse_status": "empty"},
            )
        return ExternalAnalysisResult(
            status=ExternalAnalysisStatus.FAILED_TECHNICAL,
            error_code="EXTERNAL_RESPONSE_PARSE_FAILED",
            error_message="provider response was not a JSON object",
            additional_fields={
                **meta,
                **response_trace_metadata(raw_text=raw_text),
                "parse_status": "not_object",
            },
            raw_reference=response_trace_metadata(raw_text=raw_text).get(
                "provider_response_sha256"
            ),
        )

    if _looks_like_hybrid_v21(parsed):
        schema_err = build_external_schema_validation_error(
            phase="schema_validate",
            reason_code="HYBRID_SCHEMA_MISMATCH",
            field="entities",
            expected_type="external_fallback_label",
            received_type="GlobalEntityResponseV21",
        )
        return ExternalAnalysisResult(
            status=ExternalAnalysisStatus.FAILED_TECHNICAL,
            error_code="EXTERNAL_SCHEMA_INVALID",
            error_message=(
                "provider returned GlobalEntityResponseV21 hybrid schema; "
                "external fallback expects status/internal_code/quantity"
            ),
            normalized_result={
                "schema": "GlobalEntityResponseV21",
                "entity_count": len(parsed.get("entities") or [])
                if isinstance(parsed.get("entities"), list)
                else None,
            },
            additional_fields={
                **meta,
                **response_trace_metadata(raw_text=raw_text),
                "parse_status": "hybrid_schema_mismatch",
                "schema_validation": schema_err,
            },
            raw_reference=response_trace_metadata(raw_text=raw_text).get(
                "provider_response_sha256"
            ),
        )

    status_raw = str(parsed.get("status") or "").strip().upper()
    code = _extract_code(parsed)
    qty_raw = parsed.get("quantity")
    if qty_raw is None:
        qty_raw = parsed.get("cantidad")
    if qty_raw is None:
        qty_raw = parsed.get("qty")
    qty = _coerce_quantity(qty_raw)
    if qty_raw is not None and qty is None:
        schema_err = build_external_schema_validation_error(
            phase="schema_validate",
            reason_code="INVALID_TYPE",
            field="quantity",
            expected_type="integer",
            received_type=type(qty_raw).__name__,
        )
        return ExternalAnalysisResult(
            status=ExternalAnalysisStatus.FAILED_TECHNICAL,
            error_code="EXTERNAL_SCHEMA_INVALID",
            error_message="quantity must be an integer",
            additional_fields={
                **meta,
                **response_trace_metadata(raw_text=raw_text),
                "schema_validation": schema_err,
            },
            raw_reference=response_trace_metadata(raw_text=raw_text).get(
                "provider_response_sha256"
            ),
        )

    confidence = parsed.get("confidence")
    confidence_f: float | None
    if confidence is None:
        confidence_f = None
    else:
        try:
            confidence_f = float(confidence)
        except (TypeError, ValueError):
            schema_err = build_external_schema_validation_error(
                phase="schema_validate",
                reason_code="INVALID_TYPE",
                field="confidence",
                expected_type="number",
                received_type=type(confidence).__name__,
            )
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                error_code="EXTERNAL_SCHEMA_INVALID",
                error_message="confidence must be a number",
                additional_fields={
                    **meta,
                    **response_trace_metadata(raw_text=raw_text),
                    "schema_validation": schema_err,
                },
                raw_reference=response_trace_metadata(raw_text=raw_text).get(
                    "provider_response_sha256"
                ),
            )

    warnings_raw = parsed.get("warnings")
    warnings: list[Any] = list(warnings_raw) if isinstance(warnings_raw, list) else []
    reason = str(parsed.get("reason"))[:200] if parsed.get("reason") else None

    if status_raw in {s.value for s in ExternalAnalysisStatus}:
        status = ExternalAnalysisStatus(status_raw)
    elif status_raw in ("OK", "SUCCESS", "RESOLVED"):
        status = ExternalAnalysisStatus.VALID
    elif not status_raw and (code or qty is not None):
        status = ExternalAnalysisStatus.VALID
    elif not status_raw and not code and qty is None:
        status = ExternalAnalysisStatus.NO_RESULT
    else:
        schema_err = build_external_schema_validation_error(
            phase="schema_validate",
            reason_code="UNKNOWN_STATUS",
            field="status",
            expected_type="ExternalAnalysisStatus",
            received_type="string",
        )
        return ExternalAnalysisResult(
            status=ExternalAnalysisStatus.FAILED_TECHNICAL,
            error_code="EXTERNAL_SCHEMA_INVALID",
            error_message="unknown status value",
            normalized_result={
                "status": status_raw or None,
                "internal_code": code,
                "quantity": qty,
            },
            additional_fields={
                **meta,
                **response_trace_metadata(raw_text=raw_text),
                "schema_validation": schema_err,
            },
            raw_reference=response_trace_metadata(raw_text=raw_text).get(
                "provider_response_sha256"
            ),
        )

    normalized = {
        "status": status.value,
        "internal_code": code,
        "quantity": qty,
        "confidence": confidence_f,
        "warnings": [str(w) for w in warnings][:20],
        "reason": reason,
    }
    meta["normalized_code_present"] = bool(code)
    meta["normalized_quantity_present"] = qty is not None
    meta["provider_declared_no_result"] = status is ExternalAnalysisStatus.NO_RESULT

    error_code = None
    error_message = None
    if status is ExternalAnalysisStatus.NO_RESULT:
        error_code = "EXTERNAL_NO_RESULT"
        error_message = reason or "Provider declared no usable label"
    elif status is ExternalAnalysisStatus.INVALID:
        error_code = "EXTERNAL_RESULT_EMPTY"
        error_message = reason or "Provider marked result INVALID"

    return ExternalAnalysisResult(
        status=status,
        internal_code=code,
        quantity=qty,
        confidence=confidence_f,
        warnings=[str(w) for w in warnings][:20],
        error_code=error_code,
        error_message=error_message,
        normalized_result=normalized,
        additional_fields=meta,
    )


def _map_llm_provider_error(exc: LLMProviderError) -> tuple[ExternalAnalysisStatus, str]:
    code = str(getattr(exc, "code", "") or "").upper()
    if "TIMEOUT" in code:
        return ExternalAnalysisStatus.TIMEOUT, "EXTERNAL_PROVIDER_TIMEOUT"
    if "RATE" in code or "429" in code:
        return ExternalAnalysisStatus.RATE_LIMITED, "EXTERNAL_PROVIDER_RATE_LIMITED"
    if "AUTH" in code or "401" in code or "403" in code:
        return ExternalAnalysisStatus.FAILED_TECHNICAL, "EXTERNAL_PROVIDER_AUTH_FAILED"
    if "MODEL" in code or "NOT_FOUND" in code or "404" in code:
        return ExternalAnalysisStatus.FAILED_TECHNICAL, "EXTERNAL_PROVIDER_MODEL_NOT_FOUND"
    if "INVALID_JSON" in code or "PARSE" in code:
        return ExternalAnalysisStatus.FAILED_TECHNICAL, "EXTERNAL_RESPONSE_PARSE_FAILED"
    if "SCHEMA" in code:
        return ExternalAnalysisStatus.FAILED_TECHNICAL, "EXTERNAL_SCHEMA_INVALID"
    if "BLOCK" in code or "SAFETY" in code:
        return ExternalAnalysisStatus.FAILED_TECHNICAL, "EXTERNAL_CONTENT_BLOCKED"
    return ExternalAnalysisStatus.FAILED_TECHNICAL, code or "EXTERNAL_PROVIDER_ERROR"


class LlmExternalImageAnalysisProvider:
    """Single-image external fallback via Gemini structured fallback schema (or other LLMs)."""

    def __init__(
        self,
        *,
        settings: Any,
        provider_name: str,
        model_name: str | None = None,
        cost_estimator: ExternalCostEstimator | None = None,
    ) -> None:
        self._settings = settings
        self._provider_name = (provider_name or "").strip().lower()
        self._model_name = (model_name or "").strip() or None
        self._cost_estimator = cost_estimator or ExternalCostEstimator()
        if not self._provider_name:
            raise ValueError("EXTERNAL_FALLBACK_PROVIDER is required when fallback is enabled")

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        if self._model_name:
            return self._model_name
        if self._provider_name == "gemini":
            return str(getattr(self._settings, "gemini_model_name", "") or "default")
        return "default"

    def analyze_image(
        self,
        image: ExternalImageInput,
        context: ExternalAnalysisContext,
    ) -> ExternalAnalysisResult:
        started = time.perf_counter()
        prompt = build_external_fallback_prompt(
            client_rules=context.extra.get("client_rules")
            if isinstance(context.extra.get("client_rules"), dict)
            else None
        )
        prompt_version = context.prompt_version or EXTERNAL_FALLBACK_PROMPT_VERSION
        requested_model = self._model_name
        executed_model = self.model_name

        try:
            prepared = self._prepare_image_bytes(image.content, context.max_image_dimension)
        except ValueError as exc:
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name=self._provider_name,
                model_name=executed_model,
                prompt_version=prompt_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="EXTERNAL_IMAGE_INVALID",
                error_message=_sanitize_message(str(exc)),
                additional_fields={
                    "requested_model": requested_model,
                    "executed_model": executed_model,
                },
            )
        request_image_sha256 = hashlib.sha256(prepared).hexdigest()
        base_meta = {
            "request_image_sha256": request_image_sha256,
            "request_image_sha256_prepared": request_image_sha256,
            "request_image_bytes": len(prepared),
            "requested_model": requested_model,
            "executed_model": executed_model,
            "prompt_key": context.prompt_key,
            "prompt_version": prompt_version,
        }

        if self._provider_name == "gemini":
            result = self._analyze_gemini_structured(
                prepared=prepared,
                prompt=prompt,
                started=started,
                prompt_version=prompt_version,
                base_meta=base_meta,
            )
        else:
            result = self._analyze_via_executor(
                prepared=prepared,
                prompt=prompt,
                context=context,
                started=started,
                prompt_version=prompt_version,
                base_meta=base_meta,
            )

        merged = dict(result.additional_fields or {})
        merged.update(base_meta)
        merged["executed_model"] = result.model_name or executed_model
        result.additional_fields = merged
        if not result.model_name:
            result.model_name = executed_model
        if not result.provider_name:
            result.provider_name = self._provider_name
        if not result.prompt_version:
            result.prompt_version = prompt_version
        return result

    def _analyze_gemini_structured(
        self,
        *,
        prepared: bytes,
        prompt: str,
        started: float,
        prompt_version: str,
        base_meta: dict[str, Any],
    ) -> ExternalAnalysisResult:
        api_key = getattr(self._settings, "gemini_api_key", "") or ""
        if not api_key:
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name="gemini",
                model_name=self.model_name,
                prompt_version=prompt_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="EXTERNAL_PROVIDER_AUTH_FAILED",
                error_message="GEMINI_API_KEY not set",
                additional_fields=dict(base_meta),
            )

        from PIL import Image

        from src.llm.gemini_client import GeminiClient

        executed_model = self.model_name
        client = GeminiClient(
            api_key=api_key,
            model_name=executed_model,
            max_retries=int(getattr(self._settings, "gemini_max_retries", 3) or 3),
            retry_delay=float(getattr(self._settings, "gemini_retry_delay", 1.0) or 1.0),
        )
        try:
            with Image.open(io.BytesIO(prepared)) as img:
                img.load()
                pil = img.convert("RGB")
                raw_text = client.generate_global_analysis_structured(
                    [pil],
                    prompt,
                    ExternalFallbackLabelResponse,
                )
        except Exception as exc:
            msg = str(exc).lower()
            status = ExternalAnalysisStatus.FAILED_TECHNICAL
            error_code = "EXTERNAL_PROVIDER_ERROR"
            if "429" in str(exc) or "rate limit" in msg:
                status = ExternalAnalysisStatus.RATE_LIMITED
                error_code = "EXTERNAL_PROVIDER_RATE_LIMITED"
            elif "timeout" in msg or "timed out" in msg:
                status = ExternalAnalysisStatus.TIMEOUT
                error_code = "EXTERNAL_PROVIDER_TIMEOUT"
            elif "404" in str(exc) or "not found" in msg:
                error_code = "EXTERNAL_PROVIDER_MODEL_NOT_FOUND"
            elif "401" in str(exc) or "403" in str(exc) or "api key" in msg:
                error_code = "EXTERNAL_PROVIDER_AUTH_FAILED"
            elif "block" in msg or "safety" in msg:
                error_code = "EXTERNAL_CONTENT_BLOCKED"
            return ExternalAnalysisResult(
                status=status,
                provider_name="gemini",
                model_name=executed_model,
                prompt_version=prompt_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code=error_code,
                error_message=_sanitize_message(str(exc)),
                usage=dict(client.last_response_usage or {}),
                additional_fields=dict(base_meta),
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = dict(client.last_response_usage or {})
        if not (raw_text or "").strip():
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name="gemini",
                model_name=executed_model,
                prompt_version=prompt_version,
                duration_ms=duration_ms,
                usage=usage,
                error_code="EXTERNAL_EMPTY_RESPONSE",
                error_message="gemini returned empty text",
                additional_fields={**base_meta, "candidate_count": 0, "http_ok": True},
            )

        cleaned = _strip_markdown_fences(raw_text)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name="gemini",
                model_name=executed_model,
                prompt_version=prompt_version,
                duration_ms=duration_ms,
                usage=usage,
                error_code="EXTERNAL_RESPONSE_PARSE_FAILED",
                error_message=_sanitize_message(f"invalid JSON: {exc}"),
                additional_fields={
                    **base_meta,
                    "parse_status": "json_decode_error",
                    "raw_text_len": len(raw_text),
                },
            )

        if not isinstance(parsed, dict):
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name="gemini",
                model_name=executed_model,
                prompt_version=prompt_version,
                duration_ms=duration_ms,
                usage=usage,
                error_code="EXTERNAL_RESPONSE_PARSE_FAILED",
                error_message="JSON root must be an object",
                additional_fields={**base_meta, "parse_status": "not_object"},
            )

        mapped = parse_external_fallback_payload(parsed, raw_text=raw_text)
        provider_response_sha256 = hashlib.sha256(
            raw_text.encode("utf-8", errors="replace")
        ).hexdigest()
        estimated = self._cost_estimator.estimate(
            provider="gemini",
            model=executed_model,
            usage=usage,
            settings=self._settings,
        )
        mapped.provider_name = "gemini"
        mapped.model_name = executed_model
        mapped.prompt_version = prompt_version
        mapped.duration_ms = duration_ms
        mapped.usage = usage
        mapped.estimated_cost = estimated
        mapped.raw_reference = provider_response_sha256
        extra = dict(mapped.additional_fields or {})
        extra["provider_response_sha256"] = provider_response_sha256
        extra["response_size"] = len(raw_text)
        extra["http_ok"] = True
        mapped.additional_fields = extra
        return mapped

    def _analyze_via_executor(
        self,
        *,
        prepared: bytes,
        prompt: str,
        context: ExternalAnalysisContext,
        started: float,
        prompt_version: str,
        base_meta: dict[str, Any],
    ) -> ExternalAnalysisResult:
        try:
            executor, normalized_key = resolve_llm_executor_for_context(
                self._provider_name,
                self._settings,
                model_name=self._model_name,
            )
        except UnknownPipelineProviderError as exc:
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name=self._provider_name,
                model_name=self.model_name,
                prompt_version=prompt_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="EXTERNAL_PROVIDER_MISCONFIGURED",
                error_message=_sanitize_message(str(exc)),
                additional_fields={**dict(base_meta), "resolver_error": "unknown_provider"},
            )
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            logger.exception(
                "external_fallback.resolver_internal_error provider=%s",
                self._provider_name,
            )
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name=self._provider_name,
                model_name=self.model_name,
                prompt_version=prompt_version,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="EXTERNAL_INTERNAL_ERROR",
                error_message=_sanitize_message(str(exc)),
                additional_fields={**dict(base_meta), "resolver_error": type(exc).__name__},
            )

        with tempfile.TemporaryDirectory(prefix="ext_fallback_") as tmp:
            path = Path(tmp) / "label.jpg"
            path.write_bytes(prepared)
            metadata: dict[str, Any] = {
                "asset_id": context.asset_id,
                "execution_scope": "SINGLE_ASSET",
                "prompt_key": context.prompt_key,
                "prompt_version": prompt_version,
                "model_name": self._model_name,
                "client_id": context.client_id,
                "adapter_name": type(executor).__name__,
                "schema_version": LlmSchemaVersion.EXTERNAL_FALLBACK_V1,
            }
            apply_job_model_name_to_llm_request_metadata(
                resolved_provider_key=normalized_key,
                job_model_name=self._model_name,
                metadata=metadata,
            )
            request = LLMRequest(
                job_id=context.job_id,
                frames=[path],
                frame_refs=[context.asset_id or "asset"],
                prompt=prompt,
                schema_version=LlmSchemaVersion.EXTERNAL_FALLBACK_V1,
                metadata=metadata,
            )
            try:
                response = executor.execute(request, self._settings)
            except LLMProviderError as exc:
                status, error_code = _map_llm_provider_error(exc)
                detail_fields = dict(base_meta)
                detail_fields["provider_error_code"] = getattr(exc, "code", None)
                detail_fields["adapter_name"] = type(executor).__name__
                detail_fields["schema_version"] = LlmSchemaVersion.EXTERNAL_FALLBACK_V1
                details = getattr(exc, "details", None)
                if isinstance(details, dict):
                    for key in (
                        "provider_response_sha256",
                        "provider_response_length",
                        "provider_response_content_type",
                        "provider_request_id",
                        "provider_model",
                    ):
                        if key in details and details[key] is not None:
                            detail_fields[key] = details[key]
                    if error_code == "EXTERNAL_SCHEMA_INVALID":
                        detail_fields["schema_validation"] = (
                            build_external_schema_validation_error(
                                phase=str(details.get("phase") or "schema_validate"),
                                reason_code=str(
                                    details.get("reason_code") or "SCHEMA_INVALID"
                                ),
                                field=(
                                    str(details["field"])
                                    if details.get("field") is not None
                                    else None
                                ),
                                expected_type=(
                                    str(details["expected_type"])
                                    if details.get("expected_type") is not None
                                    else None
                                ),
                                received_type=(
                                    str(details["received_type"])
                                    if details.get("received_type") is not None
                                    else None
                                ),
                            )
                        )
                response_sha = detail_fields.get("provider_response_sha256")
                return ExternalAnalysisResult(
                    status=status,
                    provider_name=normalized_key,
                    model_name=self.model_name,
                    prompt_version=prompt_version,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_code=error_code,
                    error_message=_sanitize_message(str(exc)),
                    additional_fields=detail_fields,
                    raw_reference=str(response_sha) if response_sha else None,
                )
            except (TimeoutError, OSError, RuntimeError) as exc:
                logger.warning(
                    "external_fallback.provider_runtime_error provider=%s err=%s",
                    normalized_key,
                    type(exc).__name__,
                )
                return ExternalAnalysisResult(
                    status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                    provider_name=normalized_key,
                    model_name=self.model_name,
                    prompt_version=prompt_version,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_code="EXTERNAL_PROVIDER_ERROR",
                    error_message=_sanitize_message(str(exc)),
                    additional_fields={
                        **dict(base_meta),
                        "adapter_name": type(executor).__name__,
                    },
                )
            except Exception as exc:
                logger.exception(
                    "external_fallback.unexpected_internal_error provider=%s",
                    normalized_key,
                )
                return ExternalAnalysisResult(
                    status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                    provider_name=normalized_key,
                    model_name=self.model_name,
                    prompt_version=prompt_version,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_code="EXTERNAL_INTERNAL_ERROR",
                    error_message=_sanitize_message(f"internal:{type(exc).__name__}"),
                    additional_fields={
                        **dict(base_meta),
                        "adapter_name": type(executor).__name__,
                        "internal_error_type": type(exc).__name__,
                    },
                )

        duration_ms = int((time.perf_counter() - started) * 1000)
        model = response.model or self.model_name
        usage = dict(response.usage) if response.usage else None
        estimated = self._cost_estimator.estimate(
            provider=normalized_key,
            model=model,
            usage=usage,
            settings=self._settings,
        )
        raw_text = response.raw_text
        parsed = response.parsed_json if isinstance(response.parsed_json, dict) else None
        if parsed is None and raw_text:
            try:
                loaded = json.loads(_strip_markdown_fences(raw_text))
                parsed = loaded if isinstance(loaded, dict) else None
            except json.JSONDecodeError:
                return ExternalAnalysisResult(
                    status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                    provider_name=normalized_key,
                    model_name=model,
                    prompt_version=prompt_version,
                    duration_ms=duration_ms,
                    usage=usage,
                    estimated_cost=estimated,
                    error_code="EXTERNAL_RESPONSE_PARSE_FAILED",
                    error_message="executor response was not valid JSON",
                    additional_fields=dict(base_meta),
                )

        mapped = parse_external_fallback_payload(parsed, raw_text=raw_text)
        response_material = raw_text or json.dumps(parsed or {}, sort_keys=True, default=str)
        provider_response_sha256 = hashlib.sha256(
            response_material.encode("utf-8", errors="replace")
        ).hexdigest()
        mapped.provider_name = normalized_key
        mapped.model_name = model
        mapped.prompt_version = prompt_version
        mapped.duration_ms = (
            duration_ms if response.latency_ms is None else int(response.latency_ms)
        )
        mapped.usage = usage
        mapped.estimated_cost = estimated
        mapped.raw_reference = provider_response_sha256
        extra = dict(mapped.additional_fields or {})
        extra["provider_response_sha256"] = provider_response_sha256
        mapped.additional_fields = extra
        return mapped

    def _prepare_image_bytes(self, content: bytes, max_dim: int) -> bytes:
        if not content:
            raise ValueError("empty_image")
        max_bytes = 12 * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError("image_too_large")
        try:
            from PIL import Image, ImageOps, UnidentifiedImageError
        except ImportError:
            raise ValueError("image_validation_unavailable") from None

        try:
            with Image.open(io.BytesIO(content)) as opened:
                fmt = (opened.format or "").upper()
                if fmt not in {"JPEG", "JPG", "PNG", "WEBP"}:
                    raise ValueError(f"unsupported_image_format:{fmt or 'unknown'}")
                opened.load()
                img: Image.Image = ImageOps.exif_transpose(opened)
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")
                elif img.mode == "L":
                    img = img.convert("RGB")
                w, h = img.size
                if w <= 0 or h <= 0 or w * h > 40_000_000:
                    raise ValueError("image_dimensions_invalid")
                longest = max(w, h)
                if longest > max_dim > 0:
                    scale = max_dim / float(longest)
                    img = img.resize(
                        (max(1, int(w * scale)), max(1, int(h * scale))),
                        Image.Resampling.LANCZOS,
                    )
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=85, optimize=True)
                data = out.getvalue()
                if len(data) > 8 * 1024 * 1024:
                    out = io.BytesIO()
                    img.save(out, format="JPEG", quality=70, optimize=True)
                    data = out.getvalue()
                return data
        except UnidentifiedImageError as exc:
            raise ValueError("corrupt_or_unrecognized_image") from exc
        except OSError as exc:
            raise ValueError("corrupt_or_unreadable_image") from exc


__all__ = [
    "ExternalFallbackLabelResponse",
    "LlmExternalImageAnalysisProvider",
    "parse_external_fallback_payload",
]
