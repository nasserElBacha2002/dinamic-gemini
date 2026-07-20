"""Phase 4 — Tesseract-backed InternalLabelReader (infrastructure).

Uses pytesseract with a real per-call ``timeout`` that terminates the tesseract subprocess
(not a soft logical timeout that leaves work running). Thread-safe lazy engine probe.
"""

from __future__ import annotations

import io
import logging
import threading
import time
from typing import Any

from src.application.ports.internal_label_reader import (
    InternalOcrContext,
    InternalOcrEngineTimeoutError,
    InternalOcrEngineUnavailableError,
    InternalOcrReadResult,
    OcrEngineTransientError,
    OcrTextBlock,
    PreparedImage,
)

logger = logging.getLogger(__name__)

ENGINE_NAME = "tesseract"

# Backward-compatible aliases
TesseractUnavailableError = InternalOcrEngineUnavailableError
TesseractTimeoutError = InternalOcrEngineTimeoutError


class TesseractInternalLabelReader:
    """Local OCR reader. Safe to share across threads; each ``read`` is independent."""

    engine_name = ENGINE_NAME

    def __init__(self, *, default_language: str = "spa+eng") -> None:
        self._default_language = default_language
        self._lock = threading.Lock()
        self._version: str | None = None
        self._probed = False
        self._probe_error: str | None = None

    @property
    def engine_version(self) -> str | None:
        """Best-effort version string. Never raises — missing Tesseract returns ``None``.

        Raising here would abort the whole job when attempt metadata is collected before
        ``process()`` (see ``SingleAssetStrategyProcessor._attempt_model``). Unavailability
        is signaled by :meth:`_ensure_available` / :meth:`read` instead.
        """
        self._probe_once()
        return self._version

    def _probe_once(self) -> None:
        if self._probed:
            return
        with self._lock:
            if self._probed:
                return
            try:
                import pytesseract

                version = str(pytesseract.get_tesseract_version())
                self._version = version
                self._probe_error = None
            except Exception as exc:
                self._probe_error = f"tesseract unavailable: {exc}"
                self._version = None
            finally:
                self._probed = True

    def _ensure_available(self) -> None:
        self._probe_once()
        if self._probe_error:
            raise InternalOcrEngineUnavailableError(self._probe_error)

    def read(
        self,
        image: PreparedImage,
        context: InternalOcrContext,
    ) -> InternalOcrReadResult:
        self._ensure_available()
        import pytesseract
        from PIL import Image

        started = time.monotonic()
        lang = (context.language or self._default_language).strip() or self._default_language
        timeout = max(1, int(context.timeout_seconds or 1))
        warnings: list[str] = []

        try:
            with Image.open(io.BytesIO(image.content)) as img:
                rgb = img.convert("RGB")
                tesseract_config = ""
                psm = getattr(context, "page_segmentation_mode", None)
                if psm is not None:
                    tesseract_config = f"--psm {int(psm)}"
                try:
                    data: dict[str, Any] = pytesseract.image_to_data(
                        rgb,
                        lang=lang,
                        config=tesseract_config,
                        output_type=pytesseract.Output.DICT,
                        timeout=timeout,
                    )
                except RuntimeError as exc:
                    # pytesseract raises RuntimeError on timeout after killing the subprocess.
                    msg = str(exc).lower()
                    if "timeout" in msg or "timed out" in msg:
                        raise InternalOcrEngineTimeoutError(
                            f"tesseract exceeded {timeout}s timeout"
                        ) from exc
                    raise
        except InternalOcrEngineTimeoutError:
            raise
        except InternalOcrEngineUnavailableError:
            raise
        except Exception as exc:
            raise OcrEngineTransientError(f"tesseract_read_failed: {exc}") from exc

        blocks = self._blocks_from_data(data)
        full_text = "\n".join(
            line
            for line in self._lines_from_data(data)
            if line.strip()
        )
        confs = [b.confidence for b in blocks if b.confidence is not None]
        agg = sum(confs) / len(confs) if confs else None
        duration_ms = int((time.monotonic() - started) * 1000)

        if not full_text.strip():
            warnings.append("OCR_EMPTY_TEXT")

        return InternalOcrReadResult(
            full_text=full_text,
            text_blocks=tuple(blocks),
            confidence=agg,
            orientation=None,
            engine_name=ENGINE_NAME,
            engine_version=self._version,
            duration_ms=duration_ms,
            warnings=tuple(warnings),
            raw_meta={
                "variant": image.variant_name,
                "lang": lang,
                "timeout_seconds": timeout,
                "psm": getattr(context, "page_segmentation_mode", None),
            },
        )

    def _blocks_from_data(self, data: dict[str, Any]) -> list[OcrTextBlock]:
        n = len(data.get("text") or [])
        blocks: list[OcrTextBlock] = []
        for i in range(n):
            text = str(data["text"][i] or "").strip()
            if not text:
                continue
            conf_raw = data.get("conf", [None] * n)[i]
            try:
                conf_f = float(conf_raw)
                conf = conf_f if conf_f >= 0 else None
            except (TypeError, ValueError):
                conf = None
            blocks.append(
                OcrTextBlock(
                    text=text,
                    confidence=conf,
                    left=_int_or_none(data.get("left", [None] * n)[i]),
                    top=_int_or_none(data.get("top", [None] * n)[i]),
                    width=_int_or_none(data.get("width", [None] * n)[i]),
                    height=_int_or_none(data.get("height", [None] * n)[i]),
                    line_num=_int_or_none(data.get("line_num", [None] * n)[i]),
                    block_num=_int_or_none(data.get("block_num", [None] * n)[i]),
                )
            )
        return blocks

    def _lines_from_data(self, data: dict[str, Any]) -> list[str]:
        n = len(data.get("text") or [])
        grouped: dict[tuple[int, int], list[tuple[int, str]]] = {}
        for i in range(n):
            text = str(data["text"][i] or "").strip()
            if not text:
                continue
            block = _int_or_none(data.get("block_num", [None] * n)[i]) or 0
            line = _int_or_none(data.get("line_num", [None] * n)[i]) or 0
            left = _int_or_none(data.get("left", [None] * n)[i]) or 0
            grouped.setdefault((block, line), []).append((left, text))
        lines: list[str] = []
        for key in sorted(grouped.keys()):
            parts = sorted(grouped[key], key=lambda t: t[0])
            lines.append(" ".join(p[1] for p in parts))
        return lines


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = [
    "ENGINE_NAME",
    "TesseractInternalLabelReader",
    "TesseractTimeoutError",
    "TesseractUnavailableError",
]
