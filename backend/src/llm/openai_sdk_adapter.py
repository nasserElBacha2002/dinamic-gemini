"""
OpenAI SDK adapter — Chat Completions + vision for hybrid global analysis v2.1 (Phase 5).

Vendor-specific code stays here; pipeline uses ``LLMRequest`` / ``LLMResponse`` only.

**Phase 9:** ``OpenAiCompatibleVendorConfig`` parameterizes this adapter for other OpenAI-compatible
HTTP APIs (e.g. DeepSeek) without changing logical ``LLMResponse.provider`` or mixing metadata keys.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionUserMessageParam

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.llm.errors import LLMProviderError
from src.llm.normalization.model_entity_id import normalize_model_entity_ids
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.response_trace import response_trace_metadata
from src.llm.schema_versions import (
    LlmSchemaVersion,
    is_external_fallback_schema,
)
from src.llm.types import LLMRequest, LLMResponse
from src.llm.vision_multimodal_payload import (
    LLM_METADATA_KEY_MULTIMODAL_ORDER,
    LLM_METADATA_KEY_REFERENCE_IMAGE_IDS,
    build_openai_vision_content_parts,
    build_openai_vision_from_serialized,
    materialize_openai_content_parts,
    resolve_serialized_payload_for_adapter,
)
from src.pipeline.services.provider_execution_errors import ProviderImageExecutionError
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)

# NOTE: Hybrid OpenAI prompts still encourage ``quantity`` / ``bbox``. ``normalize_llm_response``
# maps a **strictly positive** ``quantity`` (or qty aliases) into ``product_label_quantity`` when
# the canonical field is unset, and copies lone ``bbox`` into optional ``extent_bbox`` (not
# ``product_label_bbox``) so PALLET rows persist for UNKNOWN-SKU jobs. Prefer canonical v2.1 keys
# from the model when possible.

# Phase E1: **ProviderPromptRules** — wire-level JSON root + canonical keys appended after hybrid
# base + optional context_instruction. Must stay consistent with ``validate_global_analysis_structure_v21``
# and ``normalize_llm_response`` expectations.
_JSON_OBJECT_SUFFIX = (
    "\n\nOutput requirement: respond with a single JSON object only (no markdown fences). "
    'Root keys: "total_entities_detected" (non-negative integer) and "entities" (array). '
    "Each entity must include these canonical keys (use null when unknown): "
    "entity_type, model_entity_id, manifest_entry_id, confidence, has_boxes, "
    "position_barcode, internal_code, position_label_bbox, product_label_bbox, "
    "product_label_quantity. manifest_entry_id is the preferred evidence identifier (e.g. IMG_001). "
    "source_image_id is optional legacy compatibility only. "
    "If a position/location barcode is visible, put it in position_barcode. "
    "If quantity is explicitly printed on the product label, put it in product_label_quantity. "
    "If the product-label region is visible, provide product_label_bbox as normalized [x1,y1,x2,y2]. "
    "Do not guess. Do not omit canonical keys for detected entities. "
    "Compatibility keys quantity/bbox may appear, but canonical fields are authoritative."
)
_OPENAI_CANONICAL_ENTITY_KEYS: tuple[str, ...] = (
    "manifest_entry_id",
    "source_image_id",
    "position_barcode",
    "internal_code",
    "product_label_quantity",
    "product_label_bbox",
)


@dataclass(frozen=True)
class OpenAiCompatibleVendorConfig:
    """Wiring for Chat Completions + vision against one OpenAI-protocol-compatible endpoint.

    ``logical_provider`` is the audit/registry key (e.g. ``openai``, ``deepseek``). It must match
    request/response metadata and must **not** be confused with the HTTP host (``base_url``).
    """

    logical_provider: str
    settings_api_key_attr: str
    settings_model_attr: str
    settings_timeout_attr: str
    settings_max_side_attr: str
    model_metadata_key: str
    hybrid_compose_provider_key: str
    missing_api_key_user_message: str
    default_model_if_settings_empty: str
    raw_response_filename: str
    log_label: str
    settings_base_url_attr: str
    default_base_url: str | None


_OPENAI_VENDOR = OpenAiCompatibleVendorConfig(
    logical_provider="openai",
    settings_api_key_attr="openai_api_key",
    settings_model_attr="openai_model",
    settings_timeout_attr="openai_request_timeout_sec",
    settings_max_side_attr="openai_vision_max_image_side",
    model_metadata_key="openai_model_name",
    hybrid_compose_provider_key="openai",
    missing_api_key_user_message="OPENAI_API_KEY not set",
    default_model_if_settings_empty="gpt-4o",
    raw_response_filename="openai_raw_response.json",
    log_label="OpenAI",
    settings_base_url_attr="",
    default_base_url=None,
)


def _extract_json_text(raw: str) -> str:
    t = (raw or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _bgr_to_jpeg_data_url(
    arr: np.ndarray, max_side: int, *, jpeg_quality: int = 88
) -> str:
    from src.llm.errors import LLMProviderError
    from src.llm.multimodal_image_normalization import (
        ProviderImageNormalizationError,
        normalize_bgr_ndarray,
        provider_image_policy_for,
    )

    policy = provider_image_policy_for(
        "openai", max_dimension=max_side if max_side > 0 else 2048, jpeg_quality=jpeg_quality
    )
    try:
        data = normalize_bgr_ndarray(
            arr, source_id=None, role="primary_evidence", policy=policy
        ).data
    except ProviderImageNormalizationError as exc:
        raise LLMProviderError(
            code=exc.code,
            message=str(exc),
            details={
                "provider": "openai",
                "phase": "image_normalization",
                "source_id": exc.source_id,
                "role": exc.role,
                "retryable_class": False,
            },
        ) from exc
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _pil_to_jpeg_data_url(
    img: Any, max_side: int, *, jpeg_quality: int = 88
) -> str:
    from src.llm.errors import LLMProviderError
    from src.llm.multimodal_image_normalization import (
        ProviderImageNormalizationError,
        normalize_pil_image,
        provider_image_policy_for,
    )

    policy = provider_image_policy_for(
        "openai", max_dimension=max_side if max_side > 0 else 2048, jpeg_quality=jpeg_quality
    )
    try:
        data = normalize_pil_image(
            img, source_id=None, role="visual_reference", policy=policy
        ).data
    except ProviderImageNormalizationError as exc:
        raise LLMProviderError(
            code=exc.code,
            message=str(exc),
            details={
                "provider": "openai",
                "phase": "image_normalization",
                "source_id": exc.source_id,
                "role": exc.role,
                "retryable_class": False,
            },
        ) from exc
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _image_to_data_url(obj: Any, max_side: int, *, jpeg_quality: int = 88) -> str:
    if isinstance(obj, np.ndarray):
        return _bgr_to_jpeg_data_url(obj, max_side, jpeg_quality=jpeg_quality)
    return _pil_to_jpeg_data_url(obj, max_side, jpeg_quality=jpeg_quality)


def _openai_completion_usage_dict(completion: Any) -> dict[str, Any]:
    """Extract OpenAI completion usage as a plain ``dict`` for ``normalize_usage``.

    Top-level ``usage.model_dump()`` must return a ``dict`` or the result is empty. For nested
    fields (e.g. token details), only ``dict`` results from ``model_dump`` are stored; non-dict
    dumps are omitted so usage snapshots remain JSON-serializable (no raw SDK objects).
    """
    u = getattr(completion, "usage", None)
    if u is None:
        return {}
    model_dump = getattr(u, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        return cast(dict[str, Any], dumped) if isinstance(dumped, dict) else {}
    out: dict[str, Any] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "completion_tokens_details",
    ):
        val = getattr(u, key, None)
        if val is None:
            continue
        nested_dump = getattr(val, "model_dump", None)
        if callable(nested_dump):
            nd = nested_dump(exclude_none=True)
            if isinstance(nd, dict):
                out[key] = nd
        else:
            out[key] = val
    return out


def _openai_load_frames_nd(request: LLMRequest) -> list[np.ndarray]:
    """Load primary frames from ndarray buffers or disk paths (same behavior as pre-B8.5 inline block)."""
    if request.frames_nd and len(request.frames_nd) > 0:
        return [np.asarray(f) for f in request.frames_nd]
    frames_nd: list[np.ndarray] = []
    for p in request.frames:
        img = cv2.imread(str(p))
        if img is not None:
            frames_nd.append(img)
    return frames_nd


def _openai_effective_model(
    request: LLMRequest, settings: Any, v: OpenAiCompatibleVendorConfig
) -> str:
    meta = request.metadata or {}
    job_model = (meta.get(v.model_metadata_key) or meta.get("model_name") or "").strip()
    default_m = (
        getattr(settings, v.settings_model_attr, "") or v.default_model_if_settings_empty
    ).strip()
    return job_model or default_m


def _openai_parse_loose_json_object(
    raw_text: str,
    *,
    prov: str,
    v: OpenAiCompatibleVendorConfig,
) -> dict[str, Any]:
    """Parse provider JSON text into an object without hybrid v2.1 validation."""
    cleaned = _extract_json_text(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("%s external fallback: invalid JSON: %s", v.log_label, e)
        raise LLMProviderError(
            code="INVALID_JSON",
            message=f"Invalid JSON: {e}",
            details={"provider": prov, "schema_version": LlmSchemaVersion.EXTERNAL_FALLBACK_V1},
        ) from e
    if not isinstance(parsed, dict):
        raise LLMProviderError(
            code="INVALID_JSON",
            message="External fallback response must be a JSON object",
            details={"provider": prov, "schema_version": LlmSchemaVersion.EXTERNAL_FALLBACK_V1},
        )
    return cast(dict[str, Any], parsed)


def _openai_build_user_content(
    request: LLMRequest,
    settings: Any,
    v: OpenAiCompatibleVendorConfig,
    frames_nd: list[np.ndarray],
    max_side: int,
) -> list[dict[str, Any]]:
    meta = request.metadata or {}
    prompt_parity_mode = bool(meta.get(LLM_METADATA_KEY_PROMPT_PARITY_MODE))
    use_request_prompt = (
        request.prompt.strip() if (request.prompt and request.prompt.strip()) else None
    )
    prompt_text = (
        use_request_prompt
        if use_request_prompt is not None
        else compose_hybrid_base_from_settings(
            settings,
            pipeline_provider_key=v.hybrid_compose_provider_key,
            prompt_parity_mode=prompt_parity_mode,
        )
    )
    if request.context_instruction and str(request.context_instruction).strip():
        prompt_text = str(request.context_instruction).strip() + "\n\n" + prompt_text
    prompt_text = prompt_text + _JSON_OBJECT_SUFFIX
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    prompt_preview = prompt_text[:240].replace("\n", " ")
    logger.debug(
        "%s prompt_contract hash=%s preview=%r requested_keys=%s",
        v.log_label,
        prompt_hash,
        prompt_preview,
        _OPENAI_CANONICAL_ENTITY_KEYS,
    )

    ctx_imgs = list(request.context_images) if request.context_images else []
    ref_ids_raw = meta.get(LLM_METADATA_KEY_REFERENCE_IMAGE_IDS) or []
    reference_image_ids = (
        [str(x) for x in ref_ids_raw] if isinstance(ref_ids_raw, list) else []
    )
    frame_refs = list(request.frame_refs) if request.frame_refs else []
    try:
        serialized = resolve_serialized_payload_for_adapter(
            request,
            provider=v.logical_provider,
        )
    except ProviderImageExecutionError as exc:
        raise LLMProviderError(
            code=exc.code,
            message=exc.message,
            details=exc.to_details(),
        ) from exc
    if serialized is not None:
        parts, multimodal_order = build_openai_vision_from_serialized(
            main_prompt_text=prompt_text,
            serialized=serialized,
        )
    else:
        parts, multimodal_order = build_openai_vision_content_parts(
            main_prompt_text=prompt_text,
            context_images=ctx_imgs,
            reference_image_ids=reference_image_ids,
            primary_frames_nd=frames_nd,
            frame_refs=frame_refs,
            request_metadata=meta,
        )
    meta[LLM_METADATA_KEY_MULTIMODAL_ORDER] = multimodal_order
    jpeg_quality = int(getattr(settings, "openai_image_jpeg_quality", 88))

    def _img_url(obj: Any, side: int) -> str:
        return _image_to_data_url(obj, side, jpeg_quality=jpeg_quality)

    def _bgr_url(obj: Any, side: int) -> str:
        return _bgr_to_jpeg_data_url(obj, side, jpeg_quality=jpeg_quality)

    content = materialize_openai_content_parts(
        parts,
        image_to_data_url=_img_url,
        bgr_to_data_url=_bgr_url,
        max_side=max_side,
    )
    return content


def _openai_chat_completions_create(
    client: OpenAI,
    *,
    model_str: str,
    content: list[dict[str, Any]],
    prov: str,
    v: OpenAiCompatibleVendorConfig,
) -> tuple[Any, int]:
    """Run Chat Completions with ``json_object`` response format; returns (completion, latency_ms)."""
    t0 = time.perf_counter()
    user_message = cast(
        ChatCompletionUserMessageParam,
        {"role": "user", "content": content},
    )
    try:
        completion = client.chat.completions.create(
            model=model_str,
            messages=[user_message],
            response_format={"type": "json_object"},
        )
    except AuthenticationError as e:
        raise LLMProviderError(
            code="NOT_CONFIGURED",
            message=str(e),
            details={"provider": prov},
        ) from e
    except RateLimitError as e:
        raise LLMProviderError(
            code="RATE_LIMIT",
            message=str(e),
            details={"provider": prov},
        ) from e
    except APITimeoutError as e:
        raise LLMProviderError(
            code="TIMEOUT",
            message=str(e),
            details={"provider": prov},
        ) from e
    except APIConnectionError as e:
        raise LLMProviderError(
            code="TIMEOUT",
            message=str(e),
            details={"provider": prov},
        ) from e
    except APIError as e:
        msg_l = str(e).lower()
        sc = getattr(e, "status_code", None)
        if sc == 429 or "rate limit" in msg_l:
            raise LLMProviderError(
                code="RATE_LIMIT",
                message=str(e),
                details={"provider": prov, "status_code": sc},
            ) from e
        if sc == 401:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message=str(e),
                details={"provider": prov},
            ) from e
        raise LLMProviderError(
            code="UNKNOWN",
            message=str(e),
            details={"provider": prov, "status_code": sc},
        ) from e

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return completion, latency_ms


def _openai_parse_validate_global_analysis_json(
    raw_text: str,
    *,
    prov: str,
    v: OpenAiCompatibleVendorConfig,
    job_id: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    cleaned = _extract_json_text(raw_text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("%s global analysis: invalid JSON: %s", v.log_label, e)
        raise LLMProviderError(
            code="INVALID_JSON",
            message=f"Invalid JSON: {e}",
            details={"provider": prov},
        ) from e
    if not isinstance(parsed, dict):
        logger.warning("%s global analysis: JSON root is not an object", v.log_label)
        raise LLMProviderError(
            code="INVALID_JSON",
            message="Global analysis response must be a JSON object",
            details={"provider": prov},
        )
    data: dict[str, Any] = parsed

    if logger.isEnabledFor(logging.DEBUG):
        entities_raw = data.get("entities")
        if isinstance(entities_raw, list):
            before_presence: dict[str, int] = {k: 0 for k in _OPENAI_CANONICAL_ENTITY_KEYS}
            for ent in entities_raw:
                if not isinstance(ent, dict):
                    continue
                for key in _OPENAI_CANONICAL_ENTITY_KEYS:
                    val = ent.get(key)
                    if val is None:
                        continue
                    if isinstance(val, str) and not val.strip():
                        continue
                    before_presence[key] += 1
            logger.debug(
                "%s canonical_key_presence_before_normalize entities=%d presence=%s",
                v.log_label,
                len(entities_raw),
                before_presence,
            )

    total = data.get("total_entities_detected")
    entities = data.get("entities") or []
    if isinstance(entities, list) and isinstance(total, (int, float)) and total != len(entities):
        logger.warning(
            "%s count mismatch: total_entities_detected=%s vs len(entities)=%d; normalizing",
            v.log_label,
            total,
            len(entities),
        )
        data["total_entities_detected"] = len(entities)

    data, repair_diagnostics = normalize_model_entity_ids(data)
    repair_warnings = [d.message for d in repair_diagnostics]
    if repair_diagnostics:
        indexes = [d.index for d in repair_diagnostics]
        logger.warning(
            "%s response normalization repaired missing/duplicate model_entity_id for %d "
            "entities (provider=%s job_id=%s indexes=%s)",
            v.log_label,
            len(repair_diagnostics),
            prov,
            job_id or "",
            indexes,
        )

    try:
        validate_global_analysis_structure_v21(data)
    except GlobalAnalysisValidationError as e:
        raise LLMProviderError(
            code="SCHEMA_INVALID",
            message=str(e),
            details={"provider": prov},
        ) from e
    return data, repair_warnings


class OpenAiSdkAdapter:
    """OpenAI Chat Completions (vision) + json_object; maps failures to ``LLMProviderError``."""

    def __init__(self, vendor_config: OpenAiCompatibleVendorConfig | None = None) -> None:
        self._v = vendor_config or _OPENAI_VENDOR

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        v = self._v
        prov = v.logical_provider
        api_key = (getattr(settings, v.settings_api_key_attr, "") or "").strip()
        if not api_key:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message=v.missing_api_key_user_message,
                details={"provider": prov},
            )

        meta = request.metadata or {}
        effective_model = _openai_effective_model(request, settings, v)

        timeout = float(getattr(settings, v.settings_timeout_attr, 120.0))
        max_side = int(getattr(settings, v.settings_max_side_attr, 2048))

        frames_nd = _openai_load_frames_nd(request)
        if not frames_nd:
            raise LLMProviderError(
                code="NO_FRAMES",
                message="No frames could be loaded",
                details={"paths_count": len(request.frames), "provider": prov},
            )

        content = _openai_build_user_content(request, settings, v, frames_nd, max_side)
        ctx_imgs = list(request.context_images) if request.context_images else []
        logger.info(
            "%s global analysis: model=%s context_images=%d primary_frames=%d",
            v.log_label,
            effective_model,
            len(ctx_imgs),
            len(frames_nd),
        )

        base_url: str | None = None
        if v.settings_base_url_attr:
            raw_u = (getattr(settings, v.settings_base_url_attr, "") or "").strip()
            base_url = raw_u or v.default_base_url
        client_kw: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            client_kw["base_url"] = base_url
        client = OpenAI(**client_kw)
        model_str: str = str(effective_model).strip()
        completion, latency_ms = _openai_chat_completions_create(
            client,
            model_str=model_str,
            content=content,
            prov=prov,
            v=v,
        )
        choice = completion.choices[0] if completion.choices else None
        raw_text = (choice.message.content or "").strip() if choice and choice.message else ""
        run_dir = meta.get("run_dir")
        if run_dir:
            p = Path(str(run_dir)) / v.raw_response_filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(raw_text, encoding="utf-8")

        if is_external_fallback_schema(request.schema_version):
            try:
                data = _openai_parse_loose_json_object(raw_text, prov=prov, v=v)
            except LLMProviderError as exc:
                details = dict(exc.details or {})
                details.update(
                    response_trace_metadata(raw_text=raw_text, provider_model=str(effective_model))
                )
                details["schema_version"] = LlmSchemaVersion.EXTERNAL_FALLBACK_V1
                raise LLMProviderError(
                    code=exc.code,
                    message=exc.message,
                    details=details,
                ) from exc
            repair_warnings: list[str] = []
        else:
            try:
                data, repair_warnings = _openai_parse_validate_global_analysis_json(
                    raw_text, prov=prov, v=v, job_id=request.job_id
                )
            except LLMProviderError as exc:
                details = dict(exc.details or {})
                details.update(
                    response_trace_metadata(raw_text=raw_text, provider_model=str(effective_model))
                )
                raise LLMProviderError(
                    code=exc.code,
                    message=exc.message,
                    details=details,
                ) from exc

        usage = _openai_completion_usage_dict(completion)
        if repair_warnings:
            usage = {**usage, "model_entity_id_repair_warnings": repair_warnings}

        return LLMResponse(
            provider=prov,
            model=str(effective_model),
            latency_ms=latency_ms,
            parsed_json=data,
            raw_text=raw_text,
            usage=usage,
        )
