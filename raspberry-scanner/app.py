#!/usr/bin/env python3
"""Local, dependency-free HTTP server for a Raspberry Pi serial scanner."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from config.repository import SnapshotRepository
from config.service import ConfigService
from config.sync import BackendSnapshotClient
from scanner_service import ScannerSession, SerialLineReader


ROOT = Path(__file__).resolve().parent


def settings_from_environment() -> tuple[str | None, int, int]:
    device = os.environ.get("SCANNER_DEVICE") or None
    baud_rate = int(os.environ.get("SCANNER_BAUD_RATE", "9600"))
    max_readings = int(os.environ.get("SCANNER_MAX_READINGS", "100"))
    return device, baud_rate, max_readings


def make_handler(session: ScannerSession, config_service: ConfigService) -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/":
                self._send_file(ROOT / "static" / "index.html", "text/html; charset=utf-8")
            elif self.path == "/api/state":
                state = session.snapshot()
                state["config"] = config_service.status()
                self._send_json(HTTPStatus.OK, state)
            elif self.path == "/api/config":
                self._send_json(HTTPStatus.OK, config_service.status())
            elif self.path == "/api/config/suppliers":
                self._send_json(HTTPStatus.OK, {"items": config_service.suppliers()})
            elif self.path.startswith("/api/config/suppliers/"):
                supplier_id = self.path.removeprefix("/api/config/suppliers/").strip()
                supplier = config_service.supplier_config(supplier_id)
                if supplier is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "supplier_not_found"})
                else:
                    self._send_json(HTTPStatus.OK, supplier)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/api/scanning/start":
                self._send_json(HTTPStatus.OK, session.start())
            elif self.path == "/api/scanning/stop":
                self._send_json(HTTPStatus.OK, session.stop())
            elif self.path == "/api/config/sync":
                self._send_json(HTTPStatus.OK, config_service.sync())
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def _send_file(self, path: Path, content_type: str) -> None:
            try:
                content = path.read_bytes()
            except OSError:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "page_unavailable"})
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, status: HTTPStatus, data: dict[str, object]) -> None:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, format: str, *args: object) -> None:
            # Keep the service log concise; scanner errors are exposed in /api/state.
            return

    return RequestHandler


def build_session(device: str | None, baud_rate: int, max_readings: int) -> ScannerSession:
    factory: Callable[[], SerialLineReader] | None = None
    if device:
        factory = lambda: SerialLineReader(device, baud_rate)
    return ScannerSession(factory, max_readings=max_readings)

def run_config_auto_sync(
    config_service: ConfigService,
    stop_event: threading.Event,
    interval_seconds: int,
    initial_delay_seconds: int,
) -> None:
    """Periodically refresh the local recognition snapshot without blocking the server."""
    if stop_event.wait(initial_delay_seconds):
        return

    while not stop_event.is_set():
        try:
            config_service.sync()
        except Exception as exc:
            # Auto-sync must never terminate the local scanner service.
            print(f"Config auto-sync failed: {exc}")

        if stop_event.wait(interval_seconds):
            return


def main() -> None:
    default_device, default_baud_rate, default_max_readings = settings_from_environment()
    parser = argparse.ArgumentParser(description="Dinamic local Raspberry scanner")
    parser.add_argument("--host", default=os.environ.get("SCANNER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SCANNER_PORT", "8080")))
    parser.add_argument("--device", default=default_device)
    parser.add_argument("--baud-rate", type=int, default=default_baud_rate)
    parser.add_argument("--max-readings", type=int, default=default_max_readings)
    args = parser.parse_args()

    session = build_session(args.device, args.baud_rate, args.max_readings)

    config_path = Path(
        os.environ.get(
            "DINAMIC_CONFIG_PATH",
            "/var/lib/dinamic-raspberry-scanner/recognition-config.json",
        )
    )
    backend_url = (os.environ.get("DINAMIC_BACKEND_URL") or "").strip()
    client_id = (os.environ.get("DINAMIC_CLIENT_ID") or "").strip() or None
    bearer_token = (os.environ.get("DINAMIC_BACKEND_BEARER_TOKEN") or "").strip() or None

    sync_interval_seconds = max(
    60,
    int(os.environ.get("DINAMIC_CONFIG_SYNC_INTERVAL_SECONDS", "900")),
    )

    sync_initial_delay_seconds = max(
        0,
        int(os.environ.get("DINAMIC_CONFIG_SYNC_INITIAL_DELAY_SECONDS", "3")),
    )

    backend_client = BackendSnapshotClient(backend_url, bearer_token) if backend_url else None
    config_service = ConfigService(SnapshotRepository(config_path), backend_client, client_id)

    sync_stop_event = threading.Event()

    sync_thread = threading.Thread(
        target=run_config_auto_sync,
        args=(
            config_service,
            sync_stop_event,
            sync_interval_seconds,
            sync_initial_delay_seconds,
        ),
        name="config-auto-sync",
        daemon=True,
    )

    server = ThreadingHTTPServer((args.host, args.port), make_handler(session, config_service))

    sync_thread.start()

    print(f"Scanner local available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        sync_stop_event.set()
        session.stop()
        server.server_close()
        sync_thread.join(timeout=2)


if __name__ == "__main__":
    main()
