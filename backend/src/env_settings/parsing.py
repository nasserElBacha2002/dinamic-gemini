"""Env parsing helpers for settings defaults (kept separate from the main config module to avoid cycles)."""

from __future__ import annotations

import os
from pathlib import Path

_DOCKER_GCP_SECRETS_PREFIX = "/app/secrets/"


def parse_max_frames_to_send() -> int | None:
    """None = sin límite (procesar todo el video). Solo límite si se define explícitamente."""
    raw = os.getenv("MAX_FRAMES_TO_SEND", "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def parse_hybrid_max_frames() -> int | None:
    """None o vacío = sin límite en modo hybrid. Valor válido 1..10000."""
    raw = (os.getenv("HYBRID_MAX_FRAMES") or "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def parse_time_limit_sec() -> float | None:
    raw = os.getenv("TIME_LIMIT_SEC", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def parse_heuristic_resize_max_side() -> int | None:
    """0 o vacío → None; valor válido → int. Evita ValueError si env está vacío."""
    raw = os.getenv("HEURISTIC_RESIZE_MAX_SIDE", "0").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def resolve_google_application_credentials_path(path: str) -> str:
    """Resolve GOOGLE_APPLICATION_CREDENTIALS for local dev vs Docker.

    Docker Compose mounts ``<repo>/secrets`` at ``/app/secrets``. When the env var
    still points at ``/app/secrets/...`` but the process runs on the host (e.g. ``./dev.sh``),
    fall back to ``<repo>/secrets/<file>`` if that file exists.
    """
    raw = (path or "").strip()
    if not raw:
        return raw
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    if raw.startswith(_DOCKER_GCP_SECRETS_PREFIX):
        name = raw[len(_DOCKER_GCP_SECRETS_PREFIX) :].lstrip("/")
        if name:
            search_roots: list[Path] = [Path.cwd(), Path.cwd().parent]
            # backend/src/env_settings/parsing.py → repo root is parents[3]
            search_roots.append(Path(__file__).resolve().parents[3])
            seen: set[Path] = set()
            for root in search_roots:
                root = root.resolve()
                if root in seen:
                    continue
                seen.add(root)
                local = (root / "secrets" / name).resolve()
                if local.is_file():
                    return str(local)
    return raw


def parse_photos_max_single_bytes() -> int | None:
    """Unset or empty → None; else int (e.g. 10*1024*1024)."""
    raw = (os.getenv("PHOTOS_MAX_SINGLE_BYTES") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None
