"""Env parsing helpers for settings defaults (kept separate from the main config module to avoid cycles)."""

from __future__ import annotations

import os
from typing import Optional


def parse_max_frames_to_send() -> Optional[int]:
    """None = sin límite (procesar todo el video). Solo límite si se define explícitamente."""
    raw = os.getenv("MAX_FRAMES_TO_SEND", "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def parse_hybrid_max_frames() -> Optional[int]:
    """None o vacío = sin límite en modo hybrid. Valor válido 1..10000."""
    raw = (os.getenv("HYBRID_MAX_FRAMES") or "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def parse_time_limit_sec() -> Optional[float]:
    raw = os.getenv("TIME_LIMIT_SEC", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def parse_heuristic_resize_max_side() -> Optional[int]:
    """0 o vacío → None; valor válido → int. Evita ValueError si env está vacío."""
    raw = os.getenv("HEURISTIC_RESIZE_MAX_SIDE", "0").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def parse_photos_max_single_bytes() -> Optional[int]:
    """Unset or empty → None; else int (e.g. 10*1024*1024)."""
    raw = (os.getenv("PHOTOS_MAX_SINGLE_BYTES") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None
