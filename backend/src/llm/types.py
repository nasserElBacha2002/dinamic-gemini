"""Global-analysis executor I/O types (provider-neutral). v3.2.4: context_instruction / context_images."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Optional extra images (e.g. visual references); concrete type is implementation-defined (often PIL).
ContextImageSequence = Sequence[Any]


class LLMRequest:
    """
    Input for one global aisle/entity analysis call (v2.1 JSON schema).

    Used as the ``LlmGlobalAnalysisExecutor`` request shape. Name is historical; fields are
    vendor-agnostic (paths, prompt text, optional in-memory frames, optional context images).
    """

    def __init__(
        self,
        job_id: str,
        frames: List[Path],
        frame_refs: List[str],
        prompt: str,
        schema_version: str,
        metadata: Optional[Dict[str, Any]] = None,
        frames_nd: Optional[List[Any]] = None,
        context_instruction: Optional[str] = None,
        context_images: Optional[ContextImageSequence] = None,
    ):
        self.job_id = job_id
        self.frames = list(frames)
        self.frame_refs = list(frame_refs)
        self.prompt = prompt
        self.schema_version = schema_version
        # Shallow copy; nested values (e.g. Phase 6 ``metadata["prompt_composition"]``) keep object identity.
        self.metadata = dict(metadata) if metadata else {}
        # Optional in-memory frames (e.g. BGR ndarray) to avoid re-loading from disk.
        self.frames_nd: Optional[List[Any]] = list(frames_nd) if frames_nd else None
        # Optional operator/inventory context (e.g. instructions + reference images) before primary frames.
        self.context_instruction: Optional[str] = context_instruction
        self.context_images: Optional[List[Any]] = list(context_images) if context_images else None


class LLMResponse:
    """
    Output of ``LlmGlobalAnalysisExecutor.execute`` (parsed v2.1 JSON + attribution).

    ``provider`` identifies the logical vendor key (e.g. ``gemini``, ``openai``, ``claude``, ``deepseek``), not an SDK type.

    ``latency_ms`` semantics are provider-defined (e.g. Claude may set this to the full multi-attempt
    window, not a single HTTP round trip); see adapter implementations.
    """

    def __init__(
        self,
        provider: str,
        model: Optional[str],
        latency_ms: Optional[int],
        parsed_json: Dict[str, Any],
        raw_text: Optional[str] = None,
        usage: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms
        self.parsed_json = parsed_json
        self.raw_text = raw_text
        self.usage = dict(usage) if usage else {}
