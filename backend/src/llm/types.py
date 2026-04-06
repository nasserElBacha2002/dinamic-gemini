"""Stage 2.2.D — LLM provider request/response types. v3.2.4: context_instruction/context_images."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# In Gemini path these are PIL.Image; kept as Sequence[Any] to avoid hard PIL dependency here.
ContextImageSequence = Sequence[Any]


class LLMRequest:
    """Input for a single global-analysis LLM call (v2.1 entity detection)."""

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
        self.metadata = dict(metadata) if metadata else {}
        # Optional in-memory frames (list of np.ndarray) to avoid re-loading from disk.
        # When provided, the pipeline executor uses these instead of loading from self.frames.
        self.frames_nd: Optional[List[Any]] = list(frames_nd) if frames_nd else None
        # v3.2.4 Phase 4: optional context (e.g. visual reference instruction + images) sent before primary frames.
        self.context_instruction: Optional[str] = context_instruction
        self.context_images: Optional[List[Any]] = list(context_images) if context_images else None


class LLMResponse:
    """Result of analyze_global: parsed v2.1 JSON and optional usage/latency."""

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
