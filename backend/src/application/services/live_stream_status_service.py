"""Optional MediaMTX path status probe (localhost API)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

LiveStreamPresence = Literal[
    "no_stream",
    "connecting",
    "live",
    "reconnecting",
    "ended",
    "service_unavailable",
]


@dataclass(frozen=True)
class LiveStreamStatusSnapshot:
    presence: LiveStreamPresence
    publisher_ready: bool
    bytes_received: int | None = None
    publish_blocked: bool = False


class LiveStreamStatusService:
    def __init__(self, *, api_base_url: str | None) -> None:
        self._api_base_url = (api_base_url or "").strip().rstrip("/") or None

    def probe(self, *, mediamtx_path: str) -> LiveStreamStatusSnapshot:
        if not self._api_base_url:
            return LiveStreamStatusSnapshot(presence="service_unavailable", publisher_ready=False)
        name = mediamtx_path.strip().lstrip("/")
        url = f"{self._api_base_url}/v3/paths/get/{urllib.parse.quote(name, safe='')}"
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return LiveStreamStatusSnapshot(presence="no_stream", publisher_ready=False)
            logger.info(
                "event=live_stream_status_probe_failed path=%s http=%s",
                name,
                exc.code,
            )
            return LiveStreamStatusSnapshot(presence="service_unavailable", publisher_ready=False)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.info("event=live_stream_status_probe_failed path=%s err=%s", name, type(exc).__name__)
            return LiveStreamStatusSnapshot(presence="service_unavailable", publisher_ready=False)

        source = payload.get("source") if isinstance(payload, dict) else None
        ready = bool(payload.get("ready")) if isinstance(payload, dict) else False
        bytes_received = None
        if isinstance(payload, dict) and isinstance(payload.get("bytesReceived"), int):
            bytes_received = int(payload["bytesReceived"])
        if source is None:
            return LiveStreamStatusSnapshot(presence="no_stream", publisher_ready=False)
        if ready:
            return LiveStreamStatusSnapshot(
                presence="live", publisher_ready=True, bytes_received=bytes_received
            )
        return LiveStreamStatusSnapshot(
            presence="connecting", publisher_ready=False, bytes_received=bytes_received
        )
