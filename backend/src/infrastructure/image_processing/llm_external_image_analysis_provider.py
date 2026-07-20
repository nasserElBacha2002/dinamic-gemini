"""Phase 5 — ExternalImageAnalysisProvider backed by existing LLM executors (one image)."""

from __future__ import annotations

import hashlib
import io
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

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
from src.llm.errors import LLMProviderError
from src.llm.types import LLMRequest
from src.pipeline.services.pipeline_provider_resolver import resolve_llm_executor_for_context

logger = logging.getLogger(__name__)


def _sanitize_message(message: str | None, *, limit: int = 500) -> str:
    text = (message or "").strip()
    for secret_marker in ("api_key", "apikey", "authorization", "bearer "):
        if secret_marker in text.lower():
            return "provider_error_redacted"
    return text[:limit]


def _parse_provider_json(parsed: dict[str, Any]) -> tuple[ExternalAnalysisStatus, dict[str, Any]]:
    status_raw = str(parsed.get("status") or "").strip().upper()
    if status_raw in {s.value for s in ExternalAnalysisStatus}:
        status = ExternalAnalysisStatus(status_raw)
    elif status_raw in ("OK", "SUCCESS", "RESOLVED"):
        status = ExternalAnalysisStatus.VALID
    elif not status_raw and (parsed.get("internal_code") or parsed.get("quantity") is not None):
        status = ExternalAnalysisStatus.VALID
    else:
        status = ExternalAnalysisStatus.NO_RESULT

    code = parsed.get("internal_code") or parsed.get("code") or parsed.get("sku")
    if isinstance(code, str):
        code = code.strip() or None
    else:
        code = None

    qty_raw = parsed.get("quantity")
    quantity: int | None
    if isinstance(qty_raw, bool):
        quantity = None
    elif isinstance(qty_raw, int):
        quantity = qty_raw
    elif isinstance(qty_raw, float) and qty_raw.is_integer():
        quantity = int(qty_raw)
    else:
        quantity = None

    confidence = parsed.get("confidence")
    try:
        confidence_f = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_f = None

    warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
    normalized = {
        "status": status.value,
        "internal_code": code,
        "quantity": quantity,
        "confidence": confidence_f,
        "warnings": [str(w) for w in warnings][:20],
        "reason": (str(parsed.get("reason"))[:200] if parsed.get("reason") else None),
    }
    return status, normalized


class LlmExternalImageAnalysisProvider:
    """Single-image analysis via the existing pipeline LLM executor registry."""

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
        return self._model_name or "default"

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
        prepared = self._prepare_image_bytes(image.content, context.max_image_dimension)
        response_hash = hashlib.sha256(prepared).hexdigest()[:32]

        try:
            executor, normalized_key = resolve_llm_executor_for_context(
                self._provider_name,
                self._settings,
                model_name=self._model_name,
            )
        except Exception as exc:
            return ExternalAnalysisResult(
                status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                provider_name=self._provider_name,
                model_name=self.model_name,
                prompt_version=context.prompt_version or EXTERNAL_FALLBACK_PROMPT_VERSION,
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code="EXTERNAL_PROVIDER_MISCONFIGURED",
                error_message=_sanitize_message(str(exc)),
                raw_reference=response_hash,
            )

        with tempfile.TemporaryDirectory(prefix="ext_fallback_") as tmp:
            path = Path(tmp) / "label.jpg"
            path.write_bytes(prepared)
            request = LLMRequest(
                job_id=context.job_id,
                frames=[path],
                frame_refs=[context.asset_id or image.asset_id or "asset"],
                prompt=prompt,
                schema_version="external_fallback_v1",
                metadata={
                    "asset_id": context.asset_id,
                    "execution_scope": "SINGLE_ASSET",
                    "prompt_key": context.prompt_key,
                    "prompt_version": context.prompt_version
                    or EXTERNAL_FALLBACK_PROMPT_VERSION,
                    "model_name": self._model_name,
                },
            )
            try:
                response = executor.execute(request, self._settings)
            except LLMProviderError as exc:
                code = str(getattr(exc, "code", "") or "").upper()
                status = ExternalAnalysisStatus.FAILED_TECHNICAL
                if "TIMEOUT" in code:
                    status = ExternalAnalysisStatus.TIMEOUT
                elif "RATE" in code:
                    status = ExternalAnalysisStatus.RATE_LIMITED
                return ExternalAnalysisResult(
                    status=status,
                    provider_name=normalized_key,
                    model_name=self.model_name,
                    prompt_version=context.prompt_version or EXTERNAL_FALLBACK_PROMPT_VERSION,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_code=code or "EXTERNAL_PROVIDER_FAILED",
                    error_message=_sanitize_message(str(exc)),
                    raw_reference=response_hash,
                )
            except Exception as exc:
                return ExternalAnalysisResult(
                    status=ExternalAnalysisStatus.FAILED_TECHNICAL,
                    provider_name=normalized_key,
                    model_name=self.model_name,
                    prompt_version=context.prompt_version or EXTERNAL_FALLBACK_PROMPT_VERSION,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_code="EXTERNAL_PROVIDER_FAILED",
                    error_message=_sanitize_message(str(exc)),
                    raw_reference=response_hash,
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
        parsed = response.parsed_json if isinstance(response.parsed_json, dict) else {}
        status, normalized = _parse_provider_json(parsed)
        return ExternalAnalysisResult(
            status=status,
            internal_code=normalized.get("internal_code"),
            quantity=normalized.get("quantity"),
            confidence=normalized.get("confidence"),
            warnings=list(normalized.get("warnings") or []),
            provider_name=normalized_key,
            model_name=model,
            prompt_version=context.prompt_version or EXTERNAL_FALLBACK_PROMPT_VERSION,
            duration_ms=duration_ms if response.latency_ms is None else int(response.latency_ms),
            usage=usage,
            estimated_cost=estimated,
            raw_reference=response_hash,
            normalized_result=normalized,
        )

    def _prepare_image_bytes(self, content: bytes, max_dim: int) -> bytes:
        if not content:
            raise ValueError("empty_image")
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return content[: 8 * 1024 * 1024]

        with Image.open(io.BytesIO(content)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            w, h = img.size
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
            # Soft byte cap (~8 MiB) to protect provider payloads.
            if len(data) > 8 * 1024 * 1024:
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=70, optimize=True)
                data = out.getvalue()
            return data


__all__ = ["LlmExternalImageAnalysisProvider"]
