"""
OpenAI SDK adapter — Chat Completions + vision for hybrid global analysis v2.1 (Phase 5).

Vendor-specific code stays here; pipeline uses ``LLMRequest`` / ``LLMResponse`` only.

**Phase 9:** ``OpenAiCompatibleVendorConfig`` parameterizes this adapter for other OpenAI-compatible
HTTP APIs (e.g. DeepSeek) without changing logical ``LLMResponse.provider`` or mixing metadata keys.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from src.exceptions.global_analysis_exceptions import GlobalAnalysisValidationError
from src.llm.errors import LLMProviderError
from src.llm.prompt_composer.hybrid_assembly import compose_hybrid_base_from_settings
from src.llm.prompt_composer.prompt_traceability import LLM_METADATA_KEY_PROMPT_PARITY_MODE
from src.llm.types import LLMRequest, LLMResponse
from src.validation.global_analysis_schema import validate_global_analysis_structure_v21

logger = logging.getLogger(__name__)

# NOTE: Hybrid OpenAI prompt bodies (``hybrid_profiles``) still encourage filling numbers and
# bounding boxes. ``normalize_llm_response`` (``entity_normalizer``) deliberately does **not**
# promote OpenAI ``quantity`` / ``bbox`` into ``product_label_quantity`` / ``product_label_bbox``
# because those fields are often semantically ambiguous (e.g. one pallet vs label-read qty).
# Align prompts in a follow-up so the model returns canonical keys and null when unreadable.

_JSON_OBJECT_SUFFIX = (
    "\n\nOutput requirement: respond with a single JSON object only (no markdown fences). "
    'Root keys: "total_entities_detected" (non-negative integer) and "entities" (array). '
    "Each entity must follow the v2.1 schema from the instructions above: entity_type "
    "(PALLET|EMPTY_PALLET|LOOSE_BOXES), model_entity_id (string), confidence (0..1), "
    "has_boxes (boolean), and optional bbox/quantity fields as specified."
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
    default_base_url: Optional[str]


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


def _bgr_to_jpeg_data_url(arr: np.ndarray, max_side: int) -> str:
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
    b64 = base64.standard_b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _pil_to_jpeg_data_url(img: Any, max_side: int) -> str:
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
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _image_to_data_url(obj: Any, max_side: int) -> str:
    if isinstance(obj, np.ndarray):
        return _bgr_to_jpeg_data_url(obj, max_side)
    return _pil_to_jpeg_data_url(obj, max_side)


class OpenAiSdkAdapter:
    """OpenAI Chat Completions (vision) + json_object; maps failures to ``LLMProviderError``."""

    def __init__(self, vendor_config: Optional[OpenAiCompatibleVendorConfig] = None) -> None:
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
        job_model = (meta.get(v.model_metadata_key) or "").strip()
        default_m = (getattr(settings, v.settings_model_attr, "") or v.default_model_if_settings_empty).strip()
        effective_model = job_model or default_m

        timeout = float(getattr(settings, v.settings_timeout_attr, 120.0))
        max_side = int(getattr(settings, v.settings_max_side_attr, 2048))

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
                details={"paths_count": len(request.frames), "provider": prov},
            )

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

        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt_text}]
        ctx_imgs = list(request.context_images) if request.context_images else []
        for im in ctx_imgs:
            url = _image_to_data_url(im, max_side)
            content.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})
        for nd in frames_nd:
            url = _bgr_to_jpeg_data_url(nd, max_side)
            content.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})

        logger.info(
            "%s global analysis: model=%s context_images=%d primary_frames=%d",
            v.log_label,
            effective_model,
            len(ctx_imgs),
            len(frames_nd),
        )

        base_url: Optional[str] = None
        if v.settings_base_url_attr:
            raw_u = (getattr(settings, v.settings_base_url_attr, "") or "").strip()
            base_url = raw_u or v.default_base_url
        client_kw: Dict[str, Any] = {"api_key": api_key, "timeout": timeout}
        if base_url:
            client_kw["base_url"] = base_url
        client = OpenAI(**client_kw)
        t0 = time.perf_counter()
        try:
            completion = client.chat.completions.create(
                model=effective_model,
                messages=[{"role": "user", "content": content}],
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
        choice = completion.choices[0] if completion.choices else None
        raw_text = (choice.message.content or "").strip() if choice and choice.message else ""
        run_dir = meta.get("run_dir")
        if run_dir:
            p = Path(str(run_dir)) / v.raw_response_filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(raw_text, encoding="utf-8")

        cleaned = _extract_json_text(raw_text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("%s global analysis: invalid JSON: %s", v.log_label, e)
            raise LLMProviderError(
                code="INVALID_JSON",
                message=f"Invalid JSON: {e}",
                details={"provider": prov},
            ) from e

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

        try:
            validate_global_analysis_structure_v21(data)
        except GlobalAnalysisValidationError as e:
            raise LLMProviderError(
                code="SCHEMA_INVALID",
                message=str(e),
                details={"provider": prov},
            ) from e

        usage: Dict[str, Any] = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }

        return LLMResponse(
            provider=prov,
            model=str(effective_model),
            latency_ms=latency_ms,
            parsed_json=data,
            raw_text=raw_text,
            usage=usage,
        )
