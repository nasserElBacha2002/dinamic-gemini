"""Proxy HLS from MediaMTX through the API (same-origin for browsers)."""

from __future__ import annotations

import base64
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PATH_TRAVERSAL = re.compile(r"(?:^|/)\.\.(?:/|$)")


@dataclass(frozen=True)
class HlsProxyFetchResult:
    body: bytes
    content_type: str
    cache_control: str = "no-store"


def _normalize_rel_path(path: str) -> str:
    cleaned = path.strip().lstrip("/")
    if not cleaned or _PATH_TRAVERSAL.search(cleaned):
        raise ValueError("invalid_hls_path")
    return cleaned


def rewrite_hls_playlist(
    body: str,
    *,
    proxy_entry_prefix: str,
    channel_resource_prefix: str,
) -> str:
    """Rewrite segment / variant URIs to point at the API HLS proxy."""
    entry = proxy_entry_prefix.rstrip("/") + "/"
    channel_prefix = channel_resource_prefix.strip().lstrip("/")
    out_lines: list[str] = []
    for raw in body.splitlines():
        line = raw.rstrip("\r")
        if not line or line.startswith("#"):
            out_lines.append(line)
            continue
        uri = line.strip()
        if uri.startswith("http://") or uri.startswith("https://"):
            parsed = urllib.parse.urlparse(uri)
            upstream_path = parsed.path.lstrip("/")
            if channel_prefix and upstream_path.startswith(channel_prefix + "/"):
                rel = upstream_path[len(channel_prefix) + 1 :]
            else:
                rel = upstream_path.split("/")[-1]
            try:
                rel = _normalize_rel_path(rel)
            except ValueError:
                continue
            out_lines.append(rel)
            continue
        if uri.startswith("/"):
            rel = uri.lstrip("/")
            if channel_prefix and rel.startswith(channel_prefix + "/"):
                rel = rel[len(channel_prefix) + 1 :]
            else:
                rel = rel.split("/")[-1]
            try:
                rel = _normalize_rel_path(rel)
            except ValueError:
                continue
            out_lines.append(rel)
            continue
        # Bare segment / child playlist names — resolve relative to the proxied playlist URL.
        try:
            _normalize_rel_path(uri)
        except ValueError:
            continue
        out_lines.append(uri)
    return "\n".join(out_lines) + "\n"


class LiveStreamHlsProxyService:
    def __init__(self, *, mediamtx_hls_base_url: str | None) -> None:
        self._hls_base = (mediamtx_hls_base_url or "").strip().rstrip("/") or None

    @property
    def enabled(self) -> bool:
        return self._hls_base is not None

    def fetch(
        self,
        *,
        mediamtx_path: str,
        resource: str,
        read_username: str,
        read_password: str,
        proxy_entry_prefix: str,
    ) -> HlsProxyFetchResult:
        if not self._hls_base:
            raise RuntimeError("hls_proxy_disabled")
        channel = _normalize_rel_path(mediamtx_path)
        rel_resource = _normalize_rel_path(resource)
        upstream_url = f"{self._hls_base}/{channel}/{rel_resource}"
        auth = base64.b64encode(f"{read_username}:{read_password}".encode()).decode("ascii")
        req = urllib.request.Request(
            upstream_url,
            headers={"Authorization": f"Basic {auth}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
        except urllib.error.HTTPError as exc:
            logger.info(
                "event=hls_proxy_upstream_failed path=%s resource=%s http=%s",
                channel,
                rel_resource,
                exc.code,
            )
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.info(
                "event=hls_proxy_upstream_failed path=%s resource=%s err=%s",
                channel,
                rel_resource,
                type(exc).__name__,
            )
            raise

        if rel_resource.endswith(".m3u8") or ".m3u8?" in rel_resource:
            text = body.decode("utf-8", errors="replace")
            rewritten = rewrite_hls_playlist(
                text,
                proxy_entry_prefix=proxy_entry_prefix,
                channel_resource_prefix=channel,
            )
            return HlsProxyFetchResult(
                body=rewritten.encode("utf-8"),
                content_type="application/vnd.apple.mpegurl",
            )
        return HlsProxyFetchResult(body=body, content_type=content_type or "application/octet-stream")