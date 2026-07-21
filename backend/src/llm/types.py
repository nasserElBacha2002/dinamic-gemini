"""Global-analysis executor I/O types (provider-neutral). v3.2.4: context_instruction / context_images."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.pipeline.services.provider_execution_request import ProviderExecutionRequest
    from src.pipeline.services.provider_payload_serialization import SerializedMultimodalPayload

# Optional extra images (e.g. visual references); concrete type is implementation-defined (often PIL).
ContextImageSequence = Sequence[Any]

IMAGE_EXECUTION_CONTRACT_CANONICAL_MANIFEST = "canonical_manifest"


class LLMRequest:
    """
    Input for one global aisle/entity analysis call (v2.1 JSON schema).

    Used as the ``LlmGlobalAnalysisExecutor`` request shape. Name is historical; fields are
    vendor-agnostic (paths, prompt text, optional in-memory frames, optional context images).
    """

    def __init__(  # noqa: PLR0913 — stable executor contract (B8.5)
        self,
        job_id: str,
        frames: list[Path],
        frame_refs: list[str],
        prompt: str,
        schema_version: str,
        metadata: dict[str, Any] | None = None,
        frames_nd: list[Any] | None = None,
        context_instruction: str | None = None,
        context_images: ContextImageSequence | None = None,
        provider_execution_request: ProviderExecutionRequest | None = None,
        canonical_provider_payload_required: bool = False,
        image_execution_contract: str | None = None,
    ):
        self.job_id = job_id
        self.frames = list(frames)
        self.frame_refs = list(frame_refs)
        self.prompt = prompt
        self.schema_version = schema_version
        # Shallow copy; nested values (e.g. Phase 6 ``metadata["prompt_composition"]``) keep object identity.
        self.metadata = dict(metadata) if metadata else {}
        # Optional in-memory frames (e.g. BGR ndarray) to avoid re-loading from disk.
        self.frames_nd: list[Any] | None = list(frames_nd) if frames_nd else None
        # Optional operator/inventory context (e.g. instructions + reference images) before primary frames.
        self.context_instruction: str | None = context_instruction
        self.context_images: list[Any] | None = list(context_images) if context_images else None
        # Phase 4.4: runtime-only adapter context (excluded from JSON metadata persistence).
        self.provider_execution_request = provider_execution_request
        self.canonical_provider_payload_required = bool(canonical_provider_payload_required)
        self.image_execution_contract = image_execution_contract
        self._serialized_multimodal_payload: SerializedMultimodalPayload | None = None

    @property
    def serialized_multimodal_payload(self) -> SerializedMultimodalPayload | None:
        return self._serialized_multimodal_payload

    @serialized_multimodal_payload.setter
    def serialized_multimodal_payload(self, value: SerializedMultimodalPayload | None) -> None:
        self._serialized_multimodal_payload = value


class LLMResponse:
    """
    Output of ``LlmGlobalAnalysisExecutor.execute`` (parsed v2.1 JSON + attribution).

    ``provider`` identifies the logical vendor key (e.g. ``gemini``, ``openai``, ``claude``, ``deepseek``), not an SDK type.

    ``latency_ms`` semantics are provider-defined (e.g. Claude may set this to the full multi-attempt
    window, not a single HTTP round trip); see adapter implementations.
    """

    def __init__(  # noqa: PLR0913 — stable executor contract (B8.5)
        self,
        provider: str,
        model: str | None,
        latency_ms: int | None,
        parsed_json: dict[str, Any],
        raw_text: str | None = None,
        usage: dict[str, Any] | None = None,
        schema_version: str | None = None,
    ):
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.parsed_json = parsed_json
        self.raw_text = raw_text
        self.usage = dict(usage) if usage else {}
        self.schema_version = (schema_version or "").strip() or None
