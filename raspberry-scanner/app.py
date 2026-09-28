#!/usr/bin/env python3
"""Local, dependency-free HTTP server for a Raspberry Pi serial scanner."""

from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from scanner_service import ScannerSession, SerialLineReader


ROOT = Path(__file__).resolve().parent


def settings_from_environment() -> tuple[str | None, int, int]:
    device = os.environ.get("SCANNER_DEVICE") or None
    baud_rate = int(os.environ.get("SCANNER_BAUD_RATE", "9600"))
    max_readings = int(os.environ.get("SCANNER_MAX_READINGS", "100"))
    return device, baud_rate, max_readings


def make_handler(session: ScannerSession) -> type[BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/":
                self._send_file(ROOT / "static" / "index.html", "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send_json(HTTPStatus.OK, session.snapshot())
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/api/scanning/start":
                self._send_json(HTTPStatus.OK, session.start())
            elif self.path == "/api/scanning/stop":
                self._send_json(HTTPStatus.OK, session.stop())
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
    server = ThreadingHTTPServer((args.host, args.port), make_handler(session))
    print(f"Scanner local available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.stop()
        server.server_close()


if __name__ == "__main__":
    main()
