#!/usr/bin/env python3
"""Local, dependency-free HTTP server for a Raspberry Pi serial scanner."""

from __future__ import annotations

import argparse
import json
import logging
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import quote, unquote

from config.repository import SnapshotRepository
from config.service import ConfigService
from config.sync import BackendSnapshotClient
from camera import build_camera_from_environment
from capture import CaptureError, CaptureService
from capture_session_store import CaptureSessionStore
from recognition import RecognitionService, SelectionError
from scanner_service import Reading, ScannerSession, SerialLineReader


ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


def settings_from_environment() -> tuple[str | None, int, int]:
    device = os.environ.get("SCANNER_DEVICE") or None
    baud_rate = int(os.environ.get("SCANNER_BAUD_RATE", "9600"))
    max_readings = int(os.environ.get("SCANNER_MAX_READINGS", "100"))
    return device, baud_rate, max_readings


def make_handler(
    session: ScannerSession,
    config_service: ConfigService,
    recognition_service: RecognitionService,
    capture_service: CaptureService,
    export_directory: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    selection_operation_lock = threading.Lock()

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self.path.split("?", 1)[0]

            if path == "/":
                self._send_file(
                    ROOT / "static" / "index.html",
                    "text/html; charset=utf-8",
                )
                return

            if path == "/api/state":
                state = session.snapshot()
                state["config"] = config_service.status()
                state["recognition"] = recognition_service.selection()
                state["capture"] = capture_service.snapshot()
                self._send_json(
                    HTTPStatus.OK,
                    state,
                )
                return

            if path == "/api/config":
                self._send_json(
                    HTTPStatus.OK,
                    config_service.status(),
                )
                return

            if path == "/api/selection":
                self._send_json(HTTPStatus.OK, recognition_service.selection())
                return

            if path == "/api/capture":
                self._send_json(HTTPStatus.OK, capture_service.snapshot())
                return

            if path == "/api/capture/download":
                self._send_capture_download()
                return

            if path == "/api/config/clients":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "items": config_service.clients(),
                    },
                )
                return

            client_prefix = "/api/config/clients/"

            if path.startswith(client_prefix):
                remainder = path.removeprefix(client_prefix)
                parts = [
                    unquote(part).strip()
                    for part in remainder.split("/")
                    if part.strip()
                ]

                if len(parts) == 1:
                    client_id = parts[0]
                    client = config_service.client_config(client_id)

                    if client is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "client_not_found"},
                        )
                    else:
                        self._send_json(
                            HTTPStatus.OK,
                            client,
                        )
                    return

                if (
                    len(parts) == 2
                    and parts[1] == "suppliers"
                ):
                    client_id = parts[0]
                    client = config_service.client_config(client_id)

                    if client is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "client_not_found"},
                        )
                    else:
                        self._send_json(
                            HTTPStatus.OK,
                            {
                                "items": config_service.suppliers(
                                    client_id
                                )
                            },
                        )
                    return

                if (
                    len(parts) == 3
                    and parts[1] == "suppliers"
                ):
                    client_id = parts[0]
                    supplier_id = parts[2]

                    client = config_service.client_config(client_id)

                    if client is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "client_not_found"},
                        )
                        return

                    supplier = config_service.supplier_config(
                        client_id,
                        supplier_id,
                    )

                    if supplier is None:
                        self._send_json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "supplier_not_found"},
                        )
                    else:
                        self._send_json(
                            HTTPStatus.OK,
                            supplier,
                        )
                    return

            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
            )

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            path = self.path.split("?", 1)[0]

            if path == "/api/scanning/start":
                # Serialize start against selection updates so one session never
                # begins with a selection concurrently being replaced.
                with selection_operation_lock:
                    if capture_service.snapshot()["state"] == "ACTIVE":
                        self._send_json(HTTPStatus.CONFLICT, {"error": "capture_controls_scanner"})
                        return
                    state = session.start()
                self._send_json(HTTPStatus.OK, state)
                return

            if path == "/api/scanning/stop":
                with selection_operation_lock:
                    if capture_service.snapshot()["state"] == "ACTIVE":
                        self._send_json(HTTPStatus.CONFLICT, {"error": "capture_controls_scanner"})
                        return
                    state = session.stop()
                self._send_json(HTTPStatus.OK, state)
                return

            if path == "/api/config/sync":
                self._send_json(
                    HTTPStatus.OK,
                    config_service.sync(),
                )
                return

            if path == "/api/selection":
                try:
                    payload = self._read_json_body()
                    with selection_operation_lock:
                        if capture_service.snapshot()["state"] == "ACTIVE":
                            raise SelectionError("selection_locked_while_capture_active")
                        selection = recognition_service.select(
                            payload.get("client_id"),
                            payload.get("supplier_id"),
                            scanning=bool(session.snapshot()["scanning"]),
                        )
                except SelectionError as exc:
                    self._send_json(HTTPStatus.CONFLICT if str(exc) in {"selection_locked_while_scanning", "selection_locked_while_capture_active"} else HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                    return
                self._send_json(HTTPStatus.OK, selection)
                return

            if path == "/api/capture/start":
                try:
                    payload = self._read_json_body()
                    with selection_operation_lock:
                        session_before = session.snapshot()
                        if session_before["scanner_state"] == "not_configured":
                            raise CaptureError("scanner_not_configured")
                        if session_before["scanning"]:
                            raise CaptureError("scanner_already_active")
                        capture = capture_service.start(payload.get("aisle_code"))
                        scanner_state = session.start()
                        if not scanner_state["scanning"]:
                            capture_service.abort_start("scanner_not_started")
                            LOGGER.error("scanner start failed during capture start")
                            raise CaptureError("scanner_not_started")
                except CaptureError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
                    return
                self._send_json(HTTPStatus.OK, capture)
                return

            if path == "/api/capture/finish":
                try:
                    with selection_operation_lock:
                        session.stop()
                        capture = capture_service.finish()
                except CaptureError as exc:
                    self._send_json(HTTPStatus.CONFLICT, {"error": str(exc), "capture": capture_service.snapshot()})
                    return
                self._send_json(HTTPStatus.OK, capture)
                return

            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "not_found"},
            )

        def _send_file(
            self,
            path: Path,
            content_type: str,
        ) -> None:
            try:
                content = path.read_bytes()
            except OSError:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "page_unavailable"},
                )
                return

            self.send_response(HTTPStatus.OK)
            self.send_header(
                "Content-Type",
                content_type,
            )
            self.send_header(
                "Content-Length",
                str(len(content)),
            )
            self.end_headers()
            self.wfile.write(content)

        def _send_capture_download(self) -> None:
            snapshot = capture_service.snapshot()
            filename = snapshot.get("filename")
            if (
                snapshot.get("state") != "FINISHED"
                or not isinstance(filename, str)
                or export_directory is None
            ):
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "capture_download_unavailable"},
                )
                return

            try:
                directory = export_directory.resolve()
                file_path = (directory / filename).resolve()
                if Path(filename).name != filename or not filename.endswith(".txt"):
                    raise ValueError("invalid capture filename")
                file_path.relative_to(directory)
                if not file_path.is_file():
                    raise FileNotFoundError(file_path)
                content = file_path.read_bytes()
            except (OSError, ValueError) as exc:
                LOGGER.warning(
                    "capture download unavailable filename=%r reason=%s: %s",
                    filename,
                    type(exc).__name__,
                    exc,
                )
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "capture_download_unavailable"},
                )
                return

            escaped_filename = filename.replace("\\", "\\\\").replace('"', '\\"')
            disposition = (
                f'attachment; filename="{escaped_filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", disposition)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _read_json_body(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 4096:
                raise ValueError("invalid request body")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("request body must be an object")
            return value

        def _send_json(
            self,
            status: HTTPStatus,
            data: dict[str, object],
        ) -> None:
            content = json.dumps(data).encode("utf-8")

            self.send_response(status)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header(
                "Content-Length",
                str(len(content)),
            )
            self.end_headers()
            self.wfile.write(content)

        def log_message(
            self,
            format: str,
            *args: object,
        ) -> None:
            # Keep the service log concise;
            # scanner errors are exposed in /api/state.
            return

    return RequestHandler


def build_session(
    device: str | None,
    baud_rate: int,
    max_readings: int,
    reading_policy: Callable[[str], dict[str, object]] | None = None,
    reading_listener: Callable[[Reading], None] | None = None,
    listener_error_handler: Callable[[Exception], None] | None = None,
) -> ScannerSession:
    factory: Callable[[], SerialLineReader] | None = None

    if device:
        def create_reader() -> SerialLineReader:
            return SerialLineReader(
                device,
                baud_rate,
            )
        factory = create_reader

    return ScannerSession(
        factory,
        max_readings=max_readings,
        reading_policy=reading_policy,
        reading_listener=reading_listener,
        listener_error_handler=listener_error_handler,
    )


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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    default_device, default_baud_rate, default_max_readings = (
        settings_from_environment()
    )

    parser = argparse.ArgumentParser(
        description="Dinamic local Raspberry scanner"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get(
            "SCANNER_HOST",
            "0.0.0.0",
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get(
                "SCANNER_PORT",
                "8080",
            )
        ),
    )
    parser.add_argument(
        "--device",
        default=default_device,
    )
    parser.add_argument(
        "--baud-rate",
        type=int,
        default=default_baud_rate,
    )
    parser.add_argument(
        "--max-readings",
        type=int,
        default=default_max_readings,
    )

    args = parser.parse_args()

    config_path = Path(
        os.environ.get(
            "DINAMIC_CONFIG_PATH",
            "/var/lib/dinamic-raspberry-scanner/recognition-config.json",
        )
    )

    backend_url = (
        os.environ.get("DINAMIC_BACKEND_URL") or ""
    ).strip()

    device_token = (
        os.environ.get("DINAMIC_DEVICE_TOKEN") or ""
    ).strip() or None

    sync_interval_seconds = max(
        60,
        int(
            os.environ.get(
                "DINAMIC_CONFIG_SYNC_INTERVAL_SECONDS",
                "900",
            )
        ),
    )

    sync_initial_delay_seconds = max(
        0,
        int(
            os.environ.get(
                "DINAMIC_CONFIG_SYNC_INITIAL_DELAY_SECONDS",
                "3",
            )
        ),
    )

    backend_client = (
        BackendSnapshotClient(
            backend_url,
            device_token,
        )
        if backend_url
        else None
    )

    config_service = ConfigService(
        SnapshotRepository(config_path),
        backend_client,
    )
    recognition_service = RecognitionService(config_service)
    export_directory = Path(
        os.environ.get(
            "DINAMIC_EXPORT_DIRECTORY",
            "/var/lib/dinamic-raspberry-scanner/exports",
        )
    )
    sessions_directory = Path(
        os.environ.get(
            "DINAMIC_CAPTURE_SESSIONS_DIRECTORY",
            str(export_directory.parent / "capture-sessions"),
        )
    )
    photos_root = Path(
        os.environ.get(
            "DINAMIC_PHOTOS_DIRECTORY",
            str(export_directory / "photos"),
        )
    )
    camera = build_camera_from_environment()
    session_store = (
        CaptureSessionStore(sessions_directory) if camera is not None else None
    )
    capture_service = CaptureService(
        recognition_service,
        export_directory,
        camera=camera,
        session_store=session_store,
        photos_root=photos_root,
    )
    session = build_session(
        args.device,
        args.baud_rate,
        args.max_readings,
        recognition_service.process,
        capture_service.record,
        capture_service.report_listener_error,
    )

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

    server = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(
            session,
            config_service,
            recognition_service,
            capture_service,
            export_directory,
        ),
    )

    sync_thread.start()

    print(
        f"Scanner local available at "
        f"http://{args.host}:{args.port}"
    )

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
