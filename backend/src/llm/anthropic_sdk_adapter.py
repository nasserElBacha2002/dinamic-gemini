"""
Anthropic (Claude) SDK adapter — Messages API + vision for hybrid global analysis v2.1 (Phase 8).

Vendor-specific code stays here; pipeline uses ``LLMRequest`` / ``LLMResponse`` only.

**Prompt policy (Phase 8, intentional):** Claude uses the hybrid **default** composer branch — the
same base bodies as Gemini, not the OpenAI-tuned overlay. That keeps one prompt source of truth for
this phase; a ``claude``-specific overlay in ``PROMPTS`` can be added later without changing Gemini or
OpenAI resolution rules (see ``hybrid_resolution``).

**Response shape:** We append a JSON-only instruction suffix (same *idea* as OpenAI’s text path;
wording unchanged). Claude returns plain text; we strip optional markdown fences, parse JSON,
normalize entity count drift, and validate v2.1. Shared extraction with other adapters can be
factored in a later phase; helpers below keep this file self-contained and small.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, NoReturn

import cv2
import numpy as np

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.llm.errors import LLMProviderError
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.types import LLMRequest, LLMResponse
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)

_JSON_OBJECT_SUFFIX = (
    "\n\nOutput requirement: respond with a single JSON object only (no markdown fences). "
    'Root keys: "total_entities_detected" (non-negative integer) and "entities" (array). '
    "Each entity must follow the v2.1 schema from the instructions above: entity_type "
    "(PALLET|EMPTY_PALLET|LOOSE_BOXES), model_entity_id (string), confidence (0..1), "
    "has_boxes (boolean), and optional bbox/quantity fields as specified."
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


def _raise_llm_error_from_messages_api_exception(e: BaseException) -> NoReturn:
    """Map ``client.messages.create`` failures to stable ``LLMProviderError`` codes.

    The Anthropic Python SDK does not always expose a single exception type per HTTP case across
    versions, so classification is **deliberately heuristic** (substring + status hints). Order
    matters: first match wins.

    Handled categories:
        * ``NOT_CONFIGURED`` — missing/invalid auth (401, ``authentication``, ``api_key`` in text).
        * ``RATE_LIMIT`` — 429 or rate-related wording.
        * ``TIMEOUT`` — ``timeout`` / ``timed out`` in message.
        * ``UNKNOWN`` — any other error from this call site.

    Invalid JSON / schema issues are handled separately after a successful HTTP response.
    """
    msg = str(e)
    msg_l = msg.lower()
    et = type(e).__name__
    details: Dict[str, Any] = {"provider": "claude", "error_type": et}
    if "401" in msg or "authentication" in msg_l or "api_key" in msg_l:
        raise LLMProviderError(code="NOT_CONFIGURED", message=msg, details=details) from e
    if "429" in msg or "rate" in msg_l:
        raise LLMProviderError(code="RATE_LIMIT", message=msg, details=details) from e
    if "timeout" in msg_l or "timed out" in msg_l:
        raise LLMProviderError(code="TIMEOUT", message=msg, details=details) from e
    raise LLMProviderError(code="UNKNOWN", message=msg, details=details) from e


def _parsed_v21_from_json_text(cleaned: str) -> dict:
    """Parse model JSON text, align ``total_entities_detected`` with ``entities`` length, validate v2.1."""
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning("Claude global analysis: invalid JSON: %s", e)
        raise LLMProviderError(
            code="INVALID_JSON",
            message=f"Invalid JSON: {e}",
            details={"provider": "claude"},
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
            details={"provider": "claude"},
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

    Failures from the HTTP call are mapped in ``_raise_llm_error_from_messages_api_exception``;
    post-response parse/validate errors use ``INVALID_JSON`` / ``SCHEMA_INVALID``.
    """

    def execute(self, request: LLMRequest, settings: Any) -> LLMResponse:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="anthropic package not installed",
                details={"provider": "claude"},
            ) from e

        api_key = (getattr(settings, "anthropic_api_key", "") or "").strip()
        if not api_key:
            raise LLMProviderError(
                code="NOT_CONFIGURED",
                message="ANTHROPIC_API_KEY not set",
                details={"provider": "claude"},
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
                details={"paths_count": len(request.frames), "provider": "claude"},
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
        for im in ctx_imgs:
            content.append(_anthropic_jpeg_content_block(_image_to_jpeg_bytes(im, max_side)))
        for nd in frames_nd:
            content.append(_anthropic_jpeg_content_block(_bgr_to_jpeg_bytes(nd, max_side)))

        logger.info(
            "Claude global analysis: model=%s context_images=%d primary_frames=%d",
            effective_model,
            len(ctx_imgs),
            len(frames_nd),
        )

        client = Anthropic(api_key=api_key, timeout=timeout)
        t0 = time.perf_counter()
        try:
            message = client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
            )
        except Exception as e:
            _raise_llm_error_from_messages_api_exception(e)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        raw_text = ""
        for block in getattr(message, "content", None) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                raw_text += getattr(block, "text", "") or ""

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
            latency_ms=latency_ms,
            parsed_json=data,
            raw_text=raw_text,
            usage=usage,
        )
