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
import io
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Tuple, cast

import cv2
import numpy as np

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.llm.errors import LLMProviderError
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.hybrid_profiles import CLAUDE_JSON_OUTPUT_INSTRUCTION_SUFFIX
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.types import LLMRequest, LLMResponse
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
    extraction_meta: Dict[str, Any],
) -> str:
    """Turn assistant text into a single JSON object string; raise ``INVALID_JSON`` on failure."""
    base_details: Dict[str, Any] = {
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

    candidates: List[str] = []
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


def _extract_text_and_block_meta_from_anthropic_message(message: Any) -> tuple[str, Dict[str, Any]]:
    """Concatenate assistant ``text`` blocks only; summarize all block types for logs."""
    content = getattr(message, "content", None) or []
    block_types: List[str] = []
    parts: List[str] = []
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
    meta: Dict[str, Any] = {
        "message_object_type": type(message).__name__,
        "block_count": len(content),
        "block_types": ",".join(block_types) if block_types else "",
        "extracted_text_len": len(raw_text),
    }
    return raw_text, meta


def _anthropic_jpeg_content_block(jpeg_bytes: bytes) -> Dict[str, Any]:
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


def classify_anthropic_messages_api_error(exc: BaseException) -> Tuple[str, Dict[str, Any]]:
    """Map Anthropic ``messages.create`` failures to ``LLMProviderError.code`` + detail dict.

    Preserves ``request_id`` from JSON body when present (e.g. 529 overload responses).
    """
    msg = str(exc)
    msg_l = msg.lower()
    et = type(exc).__name__
    details: Dict[str, Any] = {
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

    if status_code == 529:
        return "PROVIDER_OVERLOADED", details
    if api_error_type == "overloaded_error":
        return "PROVIDER_OVERLOADED", details
    if "overloaded_error" in msg_l or "error code: 529" in msg_l:
        return "PROVIDER_OVERLOADED", details

    if status_code == 429 or "429" in msg or "rate_limit" in msg_l or "rate limit" in msg_l:
        return "RATE_LIMIT", details

    if status_code == 401 or "401" in msg or "authentication" in msg_l or "api_key" in msg_l:
        return "NOT_CONFIGURED", details

    if "timeout" in msg_l or "timed out" in msg_l:
        return "TIMEOUT", details

    return "UNKNOWN", details


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


def _parsed_v21_from_json_text(cleaned: str, *, error_context: Dict[str, Any] | None = None) -> dict:
    """Parse model JSON text, align ``total_entities_detected`` with ``entities`` length, validate v2.1."""
    ctx: Dict[str, Any] = {"provider": "claude", "phase": "response_parse"}
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
    data = parsed

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
    return cast(Dict[str, Any], data)


def _bgr_to_jpeg_bytes(arr: np.ndarray, max_side: int) -> bytes:
    if arr is None or arr.size == 0:
        raise ValueError("empty frame")
    work = arr
    h, w = work.shape[:2]
    m = max(h, w)
    if max_side > 0 and m > max_side:
        scale = max_side / m
        work = cv2.resize(
            work,
            (max(1, int(w * scale)), max(1, int(h * scale))),
            interpolation=cv2.INTER_AREA,
        )
    ok, buf = cv2.imencode(".jpg", work, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok or buf is None:
        raise ValueError("jpeg encode failed")
    return buf.tobytes()


def _pil_to_jpeg_bytes(img: Any, max_side: int) -> bytes:
    from PIL import Image

    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    m = max(w, h)
    if max_side > 0 and m > max_side:
        scale = max_side / m
        img = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _image_to_jpeg_bytes(obj: Any, max_side: int) -> bytes:
    if isinstance(obj, np.ndarray):
        return _bgr_to_jpeg_bytes(obj, max_side)
    return _pil_to_jpeg_bytes(obj, max_side)


def _anthropic_message_usage_dict(message: Any) -> Dict[str, Any]:
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
        return cast(Dict[str, Any], dumped) if isinstance(dumped, dict) else {}
    out: Dict[str, Any] = {}
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
        prompt_parity_mode = bool(meta.get(LLM_METADATA_KEY_PROMPT_PARITY_MODE))
        job_model = (meta.get("claude_model_name") or "").strip()
        effective_model = job_model or (getattr(settings, "anthropic_model", "") or "").strip()
        if not effective_model:
            effective_model = "claude-sonnet-4-20250514"

        timeout = float(getattr(settings, "anthropic_request_timeout_sec", 120.0))
        max_side = int(getattr(settings, "anthropic_vision_max_image_side", 2048))
        max_tokens = int(getattr(settings, "anthropic_max_output_tokens", 16384))
        max_attempts = int(getattr(settings, "anthropic_max_retries", 4))
        base_delay = float(getattr(settings, "anthropic_retry_base_delay_sec", 1.0))

        if request.frames_nd and len(request.frames_nd) > 0:
            frames_nd: List[np.ndarray] = [np.asarray(f) for f in request.frames_nd]
        else:
            frames_nd = []
            for p in request.frames:
                img = cv2.imread(str(p))
                if img is not None:
                    frames_nd.append(img)
        if not frames_nd:
            raise LLMProviderError(
                code="NO_FRAMES",
                message="No frames could be loaded",
                details={"paths_count": len(request.frames), "provider": "claude", "phase": "input"},
            )

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
        prompt_text = prompt_text + _JSON_OBJECT_SUFFIX

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        ctx_imgs = list(request.context_images) if request.context_images else []
        # TODO: overload mitigation — optional reduction of context image count or quality after
        # repeated PROVIDER_OVERLOADED (requires policy + metrics; high attachment counts stress API).
        for im in ctx_imgs:
            content.append(_anthropic_jpeg_content_block(_image_to_jpeg_bytes(im, max_side)))
        for nd in frames_nd:
            content.append(_anthropic_jpeg_content_block(_bgr_to_jpeg_bytes(nd, max_side)))

        image_blocks = sum(1 for b in content if b.get("type") == "image")
        logger.info(
            "Claude phase=api_request_ready model=%s provider_family=anthropic "
            "context_images=%d primary_frames=%d total_image_attachments=%d text_blocks=1",
            effective_model,
            len(ctx_imgs),
            len(frames_nd),
            image_blocks,
        )

        client = Anthropic(api_key=api_key, timeout=timeout)
        t_cycle_start = time.perf_counter()
        message = None
        for attempt in range(max_attempts):
            try:
                logger.debug(
                    "Claude phase=api_invoke model=%s attempt=%d/%d",
                    effective_model,
                    attempt + 1,
                    max_attempts,
                )
                message = client.messages.create(
                    model=effective_model,
                    max_tokens=max_tokens,
                    messages=cast(Any, [{"role": "user", "content": content}]),
                )
                break
            except Exception as e:
                code, det = classify_anthropic_messages_api_error(e)
                retryable = _is_retryable_anthropic_classified_code(code)
                can_retry = retryable and attempt < max_attempts - 1
                logger.warning(
                    "Claude phase=api_invoke failed model=%s code=%s http_status=%s "
                    "api_error_type=%s request_id=%s attempt=%d/%d retryable=%s",
                    effective_model,
                    code,
                    det.get("http_status"),
                    det.get("api_error_type"),
                    det.get("request_id"),
                    attempt + 1,
                    max_attempts,
                    retryable,
                )
                if not can_retry:
                    _raise_llm_error_from_messages_api_exception(
                        e,
                        model=effective_model,
                        phase="api_invoke",
                        attempt_index=attempt,
                        max_attempts=max_attempts,
                    )
                delay = base_delay * (2**attempt) + random.uniform(0.0, _RETRY_JITTER_SEC)
                logger.info(
                    "Claude phase=api_invoke backing_off_sec=%.2f next_attempt=%d/%d",
                    delay,
                    attempt + 2,
                    max_attempts,
                )
                time.sleep(delay)

        if message is None:
            raise LLMProviderError(
                code="UNKNOWN",
                message="Claude messages.create returned no response after retries",
                details={"provider": "claude", "model": effective_model, "phase": "api_invoke"},
            )

        # Wall time from first attempt through last successful HTTP response (includes prior failures + backoff).
        total_attempt_window_ms = int((time.perf_counter() - t_cycle_start) * 1000)
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
        }
        json_str = _coerce_claude_response_text_to_json_string(
            raw_text,
            model=effective_model,
            extraction_meta=block_meta,
        )
        data = _parsed_v21_from_json_text(json_str, error_context=err_ctx)

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
        )
