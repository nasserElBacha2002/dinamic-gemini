"""Kick active RTMP publishers via MediaMTX Control API (localhost only)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_RTMP_SOURCE = "rtmpConn"


class LiveStreamMediaMtxControl:
    def __init__(self, *, api_base_url: str | None) -> None:
        self._api_base_url = (api_base_url or "").strip().rstrip("/") or None

    def kick_publisher(self, *, mediamtx_path: str) -> bool:
        """Best-effort disconnect of the current publisher on ``mediamtx_path``."""
        if not self._api_base_url:
            return False
        name = mediamtx_path.strip().lstrip("/")
        path_url = f"{self._api_base_url}/v3/paths/get/{urllib.parse.quote(name, safe='')}"
        try:
            with urllib.request.urlopen(path_url, timeout=2.5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            logger.info(
                "event=live_stream_kick_skipped reason=path_lookup_failed path=%s err=%s",
                name,
                type(exc).__name__,
            )
            return False
        if not isinstance(payload, dict):
            return False
        source = payload.get("source")
        if not isinstance(source, dict):
            return False
        source_type = str(source.get("type") or "").strip()
        source_id = str(source.get("id") or "").strip()
        if source_type != _RTMP_SOURCE or not source_id:
            logger.info(
                "event=live_stream_kick_skipped reason=no_rtmp_publisher path=%s type=%s",
                name,
                source_type or "none",
            )
            return False
        kick_url = f"{self._api_base_url}/v3/rtmpconns/kick/{urllib.parse.quote(source_id, safe='')}"
        try:
            req = urllib.request.Request(kick_url, method="POST", data=b"")
            with urllib.request.urlopen(req, timeout=2.5):
                logger.info("event=live_stream_publisher_kicked path=%s", name)
                return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            logger.info(
                "event=live_stream_kick_failed path=%s err=%s",
                name,
                type(exc).__name__,
            )
            return False