"""
Anthropic (Claude) SDK adapter — Messages API + vision for hybrid global analysis v2.1 (Phase 8).

Vendor-specific code stays here; pipeline uses ``LLMRequest`` / ``LLMResponse`` only.

**Prompt policy:** Claude uses the hybrid ``default`` body **plus** the registry ``claude`` supplement
(see ``hybrid_profiles`` / ``resolve_hybrid_entry_for_provider``) — canonical entity JSON contract
aligned with ``EntityV21``. It does **not** use the OpenAI-tuned replacement fragment. Gemini still
uses ``default`` only; structured output enforces schema on the Gemini path separately.

**Response shape:** We append a JSON-only instruction suffix (same *idea* as OpenAI’s text path;
wording unchanged). Claude returns ``content[]`` blocks; we concatenate **text** blocks only
(skipping ``tool_use`` / ``thinking`` / etc.), strip optional markdown fences, extract a JSON object
(fallback: first balanced ``{...}`` when the model adds prose), align entity counts, and validate v2.1.

**Capacity / overload:** HTTP 529 / ``overloaded_error`` → ``PROVIDER_OVERLOADED``; HTTP 429 →
``RATE_LIMIT``. Those codes are retried with bounded exponential backoff (see
``Settings.anthropic_max_retries``). Timeout-like transport errors map to ``TIMEOUT`` (classified
for observability) but are **not** retried here. Parsing / schema failures after a successful HTTP
response are **not** retried.

**Request size:** Large multimodal payloads (many reference + primary images) increase overload risk.
There is no automatic slimming yet — TODO: consider dropping or downsampling context images after
repeated ``PROVIDER_OVERLOADED`` (product decision).
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import cv2
import numpy as np

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.llm.errors import LLMProviderError
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.hybrid_profiles import CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.response_trace import response_trace_metadata
from src.llm.schema_versions import is_external_fallback_schema
from src.llm.types import LLMRequest, LLMResponse
from src.llm.vision_multimodal_payload import (
    LLM_METADATA_KEY_MULTIMODAL_ORDER,
    LLM_METADATA_KEY_REFERENCE_IMAGE_IDS,
    build_anthropic_message_content_parts,
    build_anthropic_vision_from_serialized,
    materialize_anthropic_content_parts,
    resolve_serialized_payload_for_adapter,
)
from src.pipeline.services.provider_execution_errors import ProviderImageExecutionError
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)

# Wire-level JSON shape + forbidden keys; semantic rules live in hybrid ``claude`` supplement + default body.
_JSON_OBJECT_SUFFIX = CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX

_RETRY_JITTER_SEC = 0.35

_JSON_PREVIEW_MAX_LEN = 240


def _safe_preview(text: str, max_len: int = _JSON_PREVIEW_MAX_LEN) -> str:
    s = (text or "").replace("\r\n", "\n")
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


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


def _first_balanced_json_object(s: str) -> str | None:
    """Return the first top-level `{...}` substring with string-aware brace matching, or None."""
    n = len(s)
    i = 0
    while i < n:
        if s[i] == "{":
            start = i
            depth = 0
            in_str = False
            esc = False
            for j in range(i, n):
                c = s[j]
                if esc:
                    esc = False
                    continue
                if in_str:
                    if c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return s[start : j + 1]
            return None
        i += 1
    return None


def _coerce_claude_response_text_to_json_string(
    raw_text: str,
    *,
    model: str,
    extraction_meta: dict[str, Any],
) -> str:
    """Turn assistant text into a single JSON object string; raise ``INVALID_JSON`` on failure."""
    base_details: dict[str, Any] = {
        "provider": "claude",
        "phase": "response_json_extract",
        "model": model,
        **extraction_meta,
    }
    stripped = (raw_text or "").strip()
    if not stripped:
        raise LLMProviderError(
            code="INVALID_JSON",
            message="Empty assistant text after extracting text blocks (expected JSON object).",
            details={
                **base_details,
                "reason": "empty_extracted_text",
                "text_preview": "",
            },
        )

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(c: str) -> None:
        c2 = c.strip()
        if c2 and c2 not in seen:
            seen.add(c2)
            candidates.append(c2)

    _add(stripped)
    _add(_extract_json_text(stripped))
    fb = _first_balanced_json_object(stripped)
    if fb:
        _add(fb)
        _add(_extract_json_text(fb))

    last_err: str | None = None
    for cand in candidates:
        try:
            json.loads(cand)
            return cand
        except json.JSONDecodeError as e:
            last_err = str(e)

    raise LLMProviderError(
        code="INVALID_JSON",
        message=f"Invalid JSON: {last_err or 'no parseable object'}",
        details={
            **base_details,
            "reason": "json_decode_failed",
            "text_preview": _safe_preview(stripped),
            "candidate_count": len(candidates),
        },
    )


def _extract_text_and_block_meta_from_anthropic_message(message: Any) -> tuple[str, dict[str, Any]]:
    """Concatenate assistant ``text`` blocks only; summarize all block types for logs."""
    content = getattr(message, "content", None) or []
    block_types: list[str] = []
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            btype = str(block.get("type") or "")
            block_types.append(btype or "?")
            if btype == "text":
                parts.append(str(block.get("text") or ""))
        else:
            btype = str(getattr(block, "type", "") or "")
            block_types.append(btype or "?")
            if btype == "text":
                parts.append(str(getattr(block, "text", "") or ""))
    raw_text = "".join(parts)
    meta: dict[str, Any] = {
        "message_object_type": type(message).__name__,
        "block_count": len(content),
        "block_types": ",".join(block_types) if block_types else "",
        "extracted_text_len": len(raw_text),
    }
    return raw_text, meta


def _anthropic_jpeg_content_block(jpeg_bytes: bytes) -> dict[str, Any]:
    """One Claude Messages API image block from JPEG bytes (shared shape for context + primary frames)."""
    b64 = base64.standard_b64encode(jpeg_bytes).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": b64,
        },
    }


def _request_id_from_anthropic_body(body: Any) -> str | None:
    if isinstance(body, dict):
        rid = body.get("request_id")
        if rid is not None and str(rid).strip():
            return str(rid).strip()
    return None


def classify_anthropic_messages_api_error(exc: BaseException) -> tuple[str, dict[str, Any]]:
    """Map Anthropic ``messages.create`` failures to ``LLMProviderError.code`` + detail dict.

    Preserves ``request_id`` from JSON body when present (e.g. 529 overload responses).
    """
    msg = str(exc)
    msg_l = msg.lower()
    et = type(exc).__name__
    details: dict[str, Any] = {
        "provider": "claude",
        "provider_family": "anthropic",
        "exception_class": et,
    }

    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        details["http_status"] = int(status_code)

    body = getattr(exc, "body", None)
    api_error_type: str | None = None
    if isinstance(body, dict):
        t = body.get("type")
        if t is not None:
            api_error_type = str(t)
            details["api_error_type"] = api_error_type
        rid = _request_id_from_anthropic_body(body)
        if rid:
            details["request_id"] = rid

    # Single exit (B8.5 PLR0911); branch order matches legacy early-return classifier.
    code = "UNKNOWN"
    if status_code == 529:
        code = "PROVIDER_OVERLOADED"
    elif api_error_type == "overloaded_error":
        code = "PROVIDER_OVERLOADED"
    elif "overloaded_error" in msg_l or "error code: 529" in msg_l:
        code = "PROVIDER_OVERLOADED"
    elif status_code == 429 or "429" in msg or "rate_limit" in msg_l or "rate limit" in msg_l:
        code = "RATE_LIMIT"
    elif status_code == 401 or "401" in msg or "authentication" in msg_l or "api_key" in msg_l:
        code = "NOT_CONFIGURED"
    elif "timeout" in msg_l or "timed out" in msg_l:
        code = "TIMEOUT"
    elif (
        "max allowed size for many-image" in msg_l
        or "image dimensions exceed" in msg_l
        or ("dimension" in msg_l and "exceed" in msg_l)
    ):
        code = "PROVIDER_IMAGE_DIMENSION_EXCEEDED"
    elif status_code == 400 and ("image" in msg_l or "multimodal" in msg_l):
        code = "PROVIDER_INVALID_MULTIMODAL_REQUEST"

    return code, details


def _is_retryable_anthropic_classified_code(code: str) -> bool:
    return code in ("PROVIDER_OVERLOADED", "RATE_LIMIT")


def _raise_llm_error_from_messages_api_exception(
    exc: BaseException,
    *,
    model: str,
    phase: str,
    attempt_index: int,
    max_attempts: int,
) -> NoReturn:
    code, details = classify_anthropic_messages_api_error(exc)
    details["model"] = model
    details["phase"] = phase
    details["attempt_index"] = attempt_index
    details["max_attempts"] = max_attempts
    details["retryable_class"] = _is_retryable_anthropic_classified_code(code)
    raise LLMProviderError(code=code, message=str(exc), details=details) from exc


def _anthropic_load_frames_nd(request: LLMRequest) -> list[np.ndarray]:
    """Load primary frames from ndarray buffers or disk paths (same behavior as pre-B8.5 inline block)."""
    if request.frames_nd and len(request.frames_nd) > 0:
        return [np.asarray(f) for f in request.frames_nd]
    frames_nd: list[np.ndarray] = []
    for p in request.frames:
        img = cv2.imread(str(p))
        if img is not None:
            frames_nd.append(img)
    return frames_nd


def _raise_from_image_normalization(exc: BaseException, *, phase: str) -> NoReturn:
    from src.llm.multimodal_image_normalization import ProviderImageNormalizationError

    if isinstance(exc, ProviderImageNormalizationError):
        raise LLMProviderError(
            code=exc.code,
            message=str(exc),
            details={
                "provider": "claude",
                "phase": phase,
                "source_id": exc.source_id,
                "role": exc.role,
                "retryable_class": False,
            },
        ) from exc
    raise LLMProviderError(
        code="PROVIDER_IMAGE_NORMALIZATION_FAILED",
        message=str(exc),
        details={"provider": "claude", "phase": phase, "retryable_class": False},
    ) from exc


def _anthropic_build_message_content(
    request: LLMRequest,
    settings: Any,
    frames_nd: list[np.ndarray],
    max_side: int,
    *,
    effective_model: str,
) -> list[dict[str, Any]]:
    from src.llm.anthropic_final_image_validation import normalize_and_validate_anthropic_content
    from src.llm.multimodal_image_normalization import (
        MultimodalNormalizationContext,
        ProviderImageNormalizationError,
        log_multimodal_request_ready,
        provider_image_policy_for,
    )

    meta = request.metadata or {}
    prompt_parity_mode = bool(meta.get(LLM_METADATA_KEY_PROMPT_PARITY_MODE))
    use_request_prompt = (
        request.prompt.strip() if (request.prompt and request.prompt.strip()) else None
    )
    prompt_text = (
        use_request_prompt
        if use_request_prompt is not None
        else compose_hybrid_base_from_settings(
            settings, pipeline_provider_key="claude", prompt_parity_mode=prompt_parity_mode
        )
    )
    if request.context_instruction and str(request.context_instruction).strip():
        prompt_text = str(request.context_instruction).strip() + "\n\n" + prompt_text
    # Hybrid GlobalEntityResponseV21 instruction must NOT be applied to single-label fallback.
    if not is_external_fallback_schema(request.schema_version):
        prompt_text = prompt_text + _JSON_OBJECT_SUFFIX

    ctx_imgs = list(request.context_images) if request.context_images else []
    ref_ids_raw = meta.get(LLM_METADATA_KEY_REFERENCE_IMAGE_IDS) or []
    reference_image_ids = (
        [str(x) for x in ref_ids_raw] if isinstance(ref_ids_raw, list) else []
    )
    frame_refs = list(request.frame_refs) if request.frame_refs else []
    try:
        serialized = resolve_serialized_payload_for_adapter(
            request,
            provider="claude",
        )
    except ProviderImageExecutionError as exc:
        raise LLMProviderError(
            code=exc.code,
            message=exc.message,
            details=exc.to_details(),
        ) from exc
    if serialized is not None:
        parts, multimodal_order = build_anthropic_vision_from_serialized(
            main_prompt_text=prompt_text,
            serialized=serialized,
        )
    else:
        parts, multimodal_order = build_anthropic_message_content_parts(
            main_prompt_text=prompt_text,
            context_images=ctx_imgs,
            reference_image_ids=reference_image_ids,
            primary_frames_nd=frames_nd,
            frame_refs=frame_refs,
            request_metadata=meta,
        )
    meta[LLM_METADATA_KEY_MULTIMODAL_ORDER] = multimodal_order
    jpeg_quality = int(getattr(settings, "anthropic_image_jpeg_quality", 88))
    policy = provider_image_policy_for(
        "claude", max_dimension=max_side, jpeg_quality=jpeg_quality
    )
    norm_ctx = MultimodalNormalizationContext()

    def _img_bytes(obj: Any, side: int) -> bytes:
        return _image_to_jpeg_bytes(
            obj, side, jpeg_quality=jpeg_quality, ctx=norm_ctx, role="visual_reference"
        )

    def _bgr_bytes(obj: Any, side: int) -> bytes:
        return _bgr_to_jpeg_bytes(
            obj, side, jpeg_quality=jpeg_quality, ctx=norm_ctx, role="primary_evidence"
        )

    try:
        content = materialize_anthropic_content_parts(
            parts,
            image_to_jpeg_bytes=_img_bytes,
            bgr_to_jpeg_bytes=_bgr_bytes,
            max_side=max_side,
            jpeg_block_factory=_anthropic_jpeg_content_block,
        )
        content, validated_blocks, block_meta = normalize_and_validate_anthropic_content(
            content,
            policy=policy,
            multimodal_order=multimodal_order,
            ctx=norm_ctx,
        )
    except ProviderImageNormalizationError as exc:
        _raise_from_image_normalization(exc, phase="final_image_validation")
    finally:
        norm_ctx.clear()

    image_blocks = sum(1 for b in content if b.get("type") == "image")
    primary_count = sum(1 for v in validated_blocks if v.role == "primary_evidence")
    reference_count = sum(1 for v in validated_blocks if v.role == "visual_reference")
    if not validated_blocks:
        largest_width = 0
        largest_height = 0
        all_validated = True
    else:
        largest_width = max(v.width for v in validated_blocks)
        largest_height = max(v.height for v in validated_blocks)
        all_validated = all(
            max(v.width, v.height) <= policy.max_dimension for v in validated_blocks
        )
    log_multimodal_request_ready(
        provider="claude",
        primary_count=primary_count or len(frames_nd),
        reference_count=reference_count or len(ctx_imgs),
        policy=policy,
        largest_width=largest_width,
        largest_height=largest_height,
        all_validated=all_validated,
        total_image_count=len(validated_blocks),
    )
    for bm in block_meta:
        logger.info(
            "anthropic_content_image_mapping",
            extra={
                "event": "anthropic_content_image_mapping",
                "content_index": bm.content_index,
                "block_type": "image",
                "role": bm.role,
                "source_id": bm.source_id,
                "manifest_entry_id": bm.manifest_entry_id,
                "reference_id": bm.reference_id,
            },
        )
    logger.info(
        "Claude phase=api_request_ready model=%s provider_family=anthropic "
        "context_images=%d primary_frames=%d total_image_attachments=%d text_blocks=1 "
        "largest_final_width=%d largest_final_height=%d all_images_validated=%s",
        effective_model,
        len(ctx_imgs),
        len(frames_nd),
        image_blocks,
        largest_width,
        largest_height,
        all_validated,
    )
    return content


@dataclass(frozen=True)
class _AnthropicMessagesInvokeParams:
    """Internal bundle for ``messages.create`` retry loop (B8.5 PLR0913)."""

    effective_model: str
    max_tokens: int
    content: list[dict[str, Any]]
    max_attempts: int
    base_delay: float


def _anthropic_invoke_messages_with_retries(
    client: Any,
    params: _AnthropicMessagesInvokeParams,
) -> tuple[Any, int]:
    """Call ``messages.create`` with retry policy; returns (message, total_attempt_window_ms)."""
    t_cycle_start = time.perf_counter()
    message = None
    for attempt in range(params.max_attempts):
        try:
            logger.debug(
                "Claude phase=api_invoke model=%s attempt=%d/%d",
                params.effective_model,
                attempt + 1,
                params.max_attempts,
            )
            message = client.messages.create(
                model=params.effective_model,
                max_tokens=params.max_tokens,
                messages=cast(Any, [{"role": "user", "content": params.content}]),
            )
            break
        except Exception as e:
            code, det = classify_anthropic_messages_api_error(e)
            retryable = _is_retryable_anthropic_classified_code(code)
            can_retry = retryable and attempt < params.max_attempts - 1
            logger.warning(
                "Claude phase=api_invoke failed model=%s code=%s http_status=%s "
                "api_error_type=%s request_id=%s attempt=%d/%d retryable=%s",
                params.effective_model,
                code,
                det.get("http_status"),
                det.get("api_error_type"),
                det.get("request_id"),
                attempt + 1,
                params.max_attempts,
                retryable,
            )
            if not can_retry:
                _raise_llm_error_from_messages_api_exception(
                    e,
                    model=params.effective_model,
                    phase="api_invoke",
                    attempt_index=attempt,
                    max_attempts=params.max_attempts,
                )
            delay = params.base_delay * (2**attempt) + random.uniform(0.0, _RETRY_JITTER_SEC)
            logger.info(
                "Claude phase=api_invoke backing_off_sec=%.2f next_attempt=%d/%d",
                delay,
                attempt + 2,
                params.max_attempts,
            )
            time.sleep(delay)

    if message is None:
        raise LLMProviderError(
            code="UNKNOWN",
            message="Claude messages.create returned no response after retries",
            details={
                "provider": "claude",
                "model": params.effective_model,
                "phase": "api_invoke",
            },
        )

    total_attempt_window_ms = int((time.perf_counter() - t_cycle_start) * 1000)
    return message, total_attempt_window_ms


def _parsed_json_object_from_text(
    cleaned: str, *, error_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse model JSON text into a JSON object (no domain-schema validation)."""
    ctx: dict[str, Any] = {"provider": "claude", "phase": "response_parse"}
    if error_context:
        ctx.update(error_context)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(
            "Claude global analysis: response_parse invalid JSON model=%s preview=%r err=%s",
            ctx.get("model"),
            ctx.get("text_preview"),
            e,
        )
        raise LLMProviderError(
            code="INVALID_JSON",
            message=f"Invalid JSON: {e}",
            details={**ctx, "parse_failure": str(e)},
        ) from e
    if not isinstance(parsed, dict):
        raise LLMProviderError(
            code="INVALID_JSON",
            message="Global analysis response must be a JSON object",
            details={**ctx, "parse_failure": "root_not_object"},
        )
    return cast(dict[str, Any], parsed)


def _parsed_v21_from_json_text(
    cleaned: str, *, error_context: dict[str, Any] | None = None
) -> dict:
    """Parse model JSON text, align ``total_entities_detected`` with ``entities`` length, validate v2.1."""
    ctx: dict[str, Any] = {"provider": "claude", "phase": "response_parse"}
    if error_context:
        ctx.update(error_context)
    data = _parsed_json_object_from_text(cleaned, error_context=error_context)

    total = data.get("total_entities_detected")
    entities = data.get("entities") or []
    if isinstance(entities, list) and isinstance(total, (int, float)) and total != len(entities):
        logger.warning(
            "Claude count mismatch: total_entities_detected=%s vs len(entities)=%d; normalizing",
            total,
            len(entities),
        )
        data["total_entities_detected"] = len(entities)

    try:
        validate_global_analysis_structure_v21(data)
    except GlobalAnalysisValidationError as e:
        raise LLMProviderError(
            code="SCHEMA_INVALID",
            message=str(e),
            details={**ctx, "phase": "schema_validate"},
        ) from e
    return cast(dict[str, Any], data)


def _bgr_to_jpeg_bytes(
    arr: np.ndarray,
    max_side: int,
    *,
    jpeg_quality: int = 88,
    ctx: Any | None = None,
    role: str = "primary_evidence",
    source_id: str | None = None,
) -> bytes:
    from src.llm.multimodal_image_normalization import (
        MultimodalNormalizationContext,
        ProviderImageNormalizationError,
        normalize_bgr_ndarray,
        provider_image_policy_for,
    )

    policy = provider_image_policy_for(
        "claude", max_dimension=max_side if max_side > 0 else 1800, jpeg_quality=jpeg_quality
    )
    local_ctx = ctx if isinstance(ctx, MultimodalNormalizationContext) else None
    try:
        return normalize_bgr_ndarray(
            arr, source_id=source_id, role=role, policy=policy, ctx=local_ctx
        ).data
    except ProviderImageNormalizationError as exc:
        _raise_from_image_normalization(exc, phase="image_normalization")


def _pil_to_jpeg_bytes(
    img: Any,
    max_side: int,
    *,
    jpeg_quality: int = 88,
    ctx: Any | None = None,
    role: str = "visual_reference",
    source_id: str | None = None,
) -> bytes:
    from src.llm.multimodal_image_normalization import (
        MultimodalNormalizationContext,
        ProviderImageNormalizationError,
        normalize_pil_image,
        provider_image_policy_for,
    )

    policy = provider_image_policy_for(
        "claude", max_dimension=max_side if max_side > 0 else 1800, jpeg_quality=jpeg_quality
    )
    local_ctx = ctx if isinstance(ctx, MultimodalNormalizationContext) else None
    try:
        return normalize_pil_image(
            img, source_id=source_id, role=role, policy=policy, ctx=local_ctx
        ).data
    except ProviderImageNormalizationError as exc:
        _raise_from_image_normalization(exc, phase="image_normalization")


def _image_to_jpeg_bytes(
    obj: Any,
    max_side: int,
    *,
    jpeg_quality: int = 88,
    ctx: Any | None = None,
    role: str = "visual_reference",
    source_id: str | None = None,
) -> bytes:
    from src.llm.multimodal_image_normalization import (
        MultimodalNormalizationContext,
        ProviderImageNormalizationError,
        normalize_multimodal_image,
        provider_image_policy_for,
    )

    if isinstance(obj, np.ndarray):
        return _bgr_to_jpeg_bytes(
            obj, max_side, jpeg_quality=jpeg_quality, ctx=ctx, role=role, source_id=source_id
        )
    if isinstance(obj, (bytes, bytearray)):
        policy = provider_image_policy_for(
            "claude",
            max_dimension=max_side if max_side > 0 else 1800,
            jpeg_quality=jpeg_quality,
        )
        local_ctx = ctx if isinstance(ctx, MultimodalNormalizationContext) else None
        try:
            return normalize_multimodal_image(
                bytes(obj),
                source_id=source_id,
                role=role,
                policy=policy,
                ctx=local_ctx,
            ).data
        except ProviderImageNormalizationError as exc:
            _raise_from_image_normalization(exc, phase="image_normalization")
    return _pil_to_jpeg_bytes(
        obj, max_side, jpeg_quality=jpeg_quality, ctx=ctx, role=role, source_id=source_id
    )


def _anthropic_message_usage_dict(message: Any) -> dict[str, Any]:
    """Serialize Anthropic message usage as a plain ``dict`` for ``normalize_usage``.

    Top-level ``usage.model_dump()`` must return a ``dict`` or the result is empty. For nested
    fields, only ``dict`` results from ``model_dump`` are stored; non-dict dumps are omitted so
    usage snapshots remain JSON-serializable (no raw SDK objects).
    """
    u = getattr(message, "usage", None)
    if u is None:
        return {}
    model_dump = getattr(u, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        return cast(dict[str, Any], dumped) if isinstance(dumped, dict) else {}
    out: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "cache_creation",
        "server_tool_use",
        "service_tier",
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


class AnthropicSdkAdapter:
    """
    Claude Messages API (vision).

    Transport errors from ``messages.create`` are classified in
    :func:`classify_anthropic_messages_api_error`; overload and rate-limit are retried (not
    ``TIMEOUT`` / auth / unknown).
    Post-response parse/validate uses ``INVALID_JSON`` / ``SCHEMA_INVALID`` (no transport retry).
    """

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="anthropic package not installed",
                details={"provider": "claude", "phase": "client_init"},
            ) from e

        api_key = (getattr(settings, "anthropic_api_key", "") or "").strip()
        if not api_key:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="ANTHROPIC_API_KEY not set",
                details={"provider": "claude", "phase": "config"},
            )

        meta = request.metadata or {}
        job_model = (
            meta.get("claude_model_name") or meta.get("model_name") or ""
        ).strip()
        effective_model = job_model or (getattr(settings, "anthropic_model", "") or "").strip()
        if not effective_model:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="Anthropic model is not configured (set EXTERNAL_FALLBACK_MODEL / ANTHROPIC_MODEL)",
                details={"provider": "claude", "phase": "config"},
            )

        timeout = float(getattr(settings, "anthropic_request_timeout_sec", 120.0))
        max_side = int(getattr(settings, "anthropic_vision_max_image_side", 1800))
        max_tokens = int(getattr(settings, "anthropic_max_output_tokens", 16384))
        max_attempts = int(getattr(settings, "anthropic_max_retries", 4))
        base_delay = float(getattr(settings, "anthropic_retry_base_delay_sec", 1.0))

        frames_nd = _anthropic_load_frames_nd(request)
        if not frames_nd:
            raise LLMProviderError(
                code="NO_FRAMES",
                message="No frames could be loaded",
                details={
                    "paths_count": len(request.frames),
                    "provider": "claude",
                    "phase": "input",
                },
            )

        content = _anthropic_build_message_content(
            request,
            settings,
            frames_nd,
            max_side,
            effective_model=effective_model,
        )

        client = Anthropic(api_key=api_key, timeout=timeout)
        message, total_attempt_window_ms = _anthropic_invoke_messages_with_retries(
            client,
            _AnthropicMessagesInvokeParams(
                effective_model=effective_model,
                max_tokens=max_tokens,
                content=content,
                max_attempts=max_attempts,
                base_delay=base_delay,
            ),
        )

        # Wall time from first attempt through last successful HTTP response (includes prior failures + backoff).
        raw_text, block_meta = _extract_text_and_block_meta_from_anthropic_message(message)

        logger.info(
            "Claude phase=response_content_extracted model=%s provider=claude "
            "message_object_type=%s block_count=%d block_types=%r extracted_text_len=%d preview=%r",
            effective_model,
            block_meta.get("message_object_type"),
            block_meta.get("block_count"),
            block_meta.get("block_types"),
            block_meta.get("extracted_text_len"),
            _safe_preview(raw_text),
        )
        logger.debug(
            "Claude phase=response_received model=%s total_attempt_window_ms=%s",
            effective_model,
            total_attempt_window_ms,
        )

        run_dir = meta.get("run_dir")
        if run_dir:
            p = Path(str(run_dir)) / "claude_raw_response.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(raw_text, encoding="utf-8")

        err_ctx = {
            "model": effective_model,
            "text_preview": _safe_preview(raw_text),
            **block_meta,
            **response_trace_metadata(raw_text=raw_text, provider_model=effective_model),
        }
        try:
            json_str = _coerce_claude_response_text_to_json_string(
                raw_text,
                model=effective_model,
                extraction_meta=block_meta,
            )
            # External single-label fallback uses a different contract than hybrid GlobalEntityResponseV21.
            if is_external_fallback_schema(request.schema_version):
                data = _parsed_json_object_from_text(json_str, error_context=err_ctx)
            else:
                data = _parsed_v21_from_json_text(json_str, error_context=err_ctx)
        except LLMProviderError as exc:
            details = dict(exc.details or {})
            details.update(
                response_trace_metadata(raw_text=raw_text, provider_model=effective_model)
            )
            raise LLMProviderError(
                code=exc.code,
                message=exc.message,
                details=details,
            ) from exc

        usage = _anthropic_message_usage_dict(message)

        return LLMResponse(
            provider="claude",
            model=str(effective_model),
            # Shared field name ``latency_ms`` carries full retry window for Claude (see debug log
            # ``total_attempt_window_ms``); not a single HTTP round-trip latency.
            latency_ms=total_attempt_window_ms,
            parsed_json=data,
            raw_text=raw_text,
            usage=usage,
            schema_version=(request.schema_version or "").strip() or None,
        )
