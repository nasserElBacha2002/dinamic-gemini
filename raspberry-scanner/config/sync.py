"""Backend transport for client-scoped recognition snapshots."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .models import RecognitionSnapshot


class SnapshotSyncError(RuntimeError):
    pass


class BackendSnapshotClient:
    def __init__(self, base_url: str, bearer_token: str | None = None, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._bearer_token = bearer_token.strip() if bearer_token else None
        self._timeout_seconds = timeout_seconds

    def fetch(self, client_id: str) -> RecognitionSnapshot:
        encoded_client_id = urllib.parse.quote(client_id, safe="")
        url = f"{self._base_url}/api/v3/clients/{encoded_client_id}/recognition-config"
        headers = {"Accept": "application/json"}
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise SnapshotSyncError(f"backend returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise SnapshotSyncError(f"backend unavailable: {exc}") from exc
        try:
            data: Any = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotSyncError("backend returned invalid JSON") from exc
        return RecognitionSnapshot.from_dict(data)
