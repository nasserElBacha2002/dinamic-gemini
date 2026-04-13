"""
Anthropic (Claude) SDK adapter — Messages API + vision for hybrid global analysis v2.1 (Phase 8).

Vendor-specific code stays here; pipeline uses ``LLMRequest`` / ``LLMResponse`` only.

**Prompt policy:** Claude uses the hybrid ``default`` body **plus** the registry ``claude`` supplement
(see ``hybrid_profiles`` / ``resolve_hybrid_entry_for_provider``) — canonical entity JSON contract
aligned with ``EntityV21``. It does **not** use the OpenAI-tuned replacement fragment. Gemini still
uses ``default`` only; structured output enforces schema on the Gemini path separately.

**Response shape:** We append a JSON-only instruction suffix (same *idea* as OpenAI’s text path;
wording unchanged). Claude returns plain text; we strip optional markdown fences, parse JSON,
normalize entity count drift, and validate v2.1.

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
from typing import Any, Dict, List, NoReturn, Tuple

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


def _parsed_v21_from_json_text(cleaned: str) -> dict:
    """Parse model JSON text, align ``total_entities_detected`` with ``entities`` length, validate v2.1."""
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("Claude global analysis: phase=response_parse invalid JSON: %s", e)
        raise LLMProviderError(
            code="INVALID_JSON",
            message=f"Invalid JSON: {e}",
            details={"provider": "claude", "phase": "response_parse"},
        ) from e

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
            details={"provider": "claude", "phase": "schema_validate"},
        ) from e
    return data


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
                    messages=[{"role": "user", "content": content}],
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
        raw_text = ""
        for block in getattr(message, "content", None) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                raw_text += getattr(block, "text", "") or ""

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

        cleaned = _extract_json_text(raw_text)
        data = _parsed_v21_from_json_text(cleaned)

        usage: Dict[str, Any] = {}
        u = getattr(message, "usage", None)
        if u is not None:
            usage = {
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
            }

        return LLMResponse(
            provider="claude",
            model=str(effective_model),
            latency_ms=total_attempt_window_ms,
            parsed_json=data,
            raw_text=raw_text,
            usage=usage,
        )
