from __future__ import annotations

import argparse
import json
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from script_utils import load_env_file
from taiwan_motorcycle_route_facade import (
    DEFAULT_PBF,
    DEFAULT_TWO_STAGE_PENALTY_SECONDS,
    MotorcycleSemanticIndex,
    annotate_route,
    load_motorcycle_semantic_index,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010
DEFAULT_VALHALLA_BASE_URL = "http://localhost:8002"
DEFAULT_TIMEOUT_S = 15.0
MAX_REQUEST_BYTES = 1_000_000


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        *,
        detail: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


class TaiwanMotorcycleApi:
    def __init__(
        self,
        *,
        valhalla_base_url: str,
        pbf_path: Path,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        two_stage_threshold_m: float = 35.0,
        lane_threshold_m: float = 20.0,
        two_stage_penalty_seconds: float = DEFAULT_TWO_STAGE_PENALTY_SECONDS,
    ) -> None:
        if not pbf_path.exists():
            raise FileNotFoundError(f"PBF does not exist: {pbf_path}")

        self.valhalla_base_url = valhalla_base_url.rstrip("/")
        self.pbf_path = pbf_path
        self.timeout_s = timeout_s
        self.two_stage_threshold_m = two_stage_threshold_m
        self.lane_threshold_m = lane_threshold_m
        self.two_stage_penalty_seconds = two_stage_penalty_seconds
        self.semantic_index = load_motorcycle_semantic_index(pbf_path)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "taiwan_motorcycle_api",
            "valhalla_base_url": self.valhalla_base_url,
            "pbf_path": str(self.pbf_path),
            "semantic_index": _index_summary(self.semantic_index),
        }

    def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._post_valhalla("route", payload)
        return annotate_route(
            response,
            self.semantic_index,
            two_stage_threshold_m=self.two_stage_threshold_m,
            lane_threshold_m=self.lane_threshold_m,
            two_stage_penalty_seconds=self.two_stage_penalty_seconds,
        )

    def trace_route(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_valhalla("trace_route", payload)

    def _post_valhalla(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.valhalla_base_url}/{action}",
                json=payload,
                timeout=self.timeout_s,
            )
        except requests.RequestException as exc:
            raise ApiError(
                HTTPStatus.BAD_GATEWAY,
                f"Valhalla {action} request failed.",
                detail=str(exc),
            ) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise ApiError(
                _upstream_status(response.status_code),
                f"Valhalla {action} failed.",
                detail={
                    "upstream_status": response.status_code,
                    "upstream_response": _decode_response_body(response.text),
                },
            )

        decoded = _decode_response_body(response.text)
        if not isinstance(decoded, dict):
            raise ApiError(
                HTTPStatus.BAD_GATEWAY,
                f"Valhalla {action} returned a non-object JSON response.",
            )
        return decoded


class TaiwanMotorcycleRequestHandler(BaseHTTPRequestHandler):
    server: "TaiwanMotorcycleHttpServer"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, self.server.api.health())
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        try:
            payload = self._read_json_body()
            if self.path == "/route":
                self._write_json(HTTPStatus.OK, self.server.api.route(payload))
                return
            if self.path == "/trace_route":
                self._write_json(HTTPStatus.OK, self.server.api.trace_route(payload))
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
        except ApiError as exc:
            self._write_json(
                exc.status,
                {
                    "error": exc.message,
                    "detail": exc.detail,
                },
            )
        except json.JSONDecodeError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "Request body must be valid JSON.",
                    "detail": str(exc),
                },
            )
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_common_headers()
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("Request body is required.")
        if content_length > MAX_REQUEST_BYTES:
            raise ApiError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "Request body is too large.",
            )

        raw_body = self.rfile.read(content_length)
        decoded = json.loads(raw_body.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("Request body must be a JSON object.")
        return decoded

    def _write_json(self, status: int | HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self._write_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_common_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


class TaiwanMotorcycleHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        api: TaiwanMotorcycleApi,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.api = api


def create_server(
    *,
    host: str,
    port: int,
    api: TaiwanMotorcycleApi,
) -> TaiwanMotorcycleHttpServer:
    return TaiwanMotorcycleHttpServer(
        (host, port),
        TaiwanMotorcycleRequestHandler,
        api,
    )


def _index_summary(index: MotorcycleSemanticIndex) -> dict[str, int]:
    return {
        "two_stage_nodes": len(index.two_stage_nodes),
        "lane_ways": len(index.lane_ways),
    }


def _decode_response_body(body: str) -> Any:
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body[:500]


def _upstream_status(status: int) -> int:
    if 400 <= status < 500:
        return status
    return int(HTTPStatus.BAD_GATEWAY)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Taiwan motorcycle navigation API facade.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--host", default=os.getenv("FACADE_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("FACADE_PORT", str(DEFAULT_PORT))),
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "VALHALLA_URL",
            os.getenv("VALHALLA_BASE_URL", DEFAULT_VALHALLA_BASE_URL),
        ),
        help="Base URL of the upstream Valhalla service.",
    )
    parser.add_argument(
        "--pbf",
        type=Path,
        default=Path(os.getenv("CUSTOM_PBF", DEFAULT_PBF)),
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("VALHALLA_TIMEOUT_S", "15")),
    )
    parser.add_argument(
        "--two-stage-threshold-m",
        type=float,
        default=float(os.getenv("TWO_STAGE_ANNOTATION_THRESHOLD_M", "35")),
    )
    parser.add_argument(
        "--lane-threshold-m",
        type=float,
        default=float(os.getenv("LANE_ANNOTATION_THRESHOLD_M", "20")),
    )
    parser.add_argument(
        "--two-stage-penalty-s",
        type=float,
        default=float(os.getenv("TWO_STAGE_TURN_PENALTY_SECONDS", "90")),
    )
    return parser


def main() -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    args = build_parser().parse_args()
    api = TaiwanMotorcycleApi(
        valhalla_base_url=args.base_url,
        pbf_path=args.pbf,
        timeout_s=args.timeout_s,
        two_stage_threshold_m=args.two_stage_threshold_m,
        lane_threshold_m=args.lane_threshold_m,
        two_stage_penalty_seconds=args.two_stage_penalty_s,
    )
    server = create_server(host=args.host, port=args.port, api=api)
    print(
        f"Taiwan motorcycle API listening on http://{args.host}:{server.server_address[1]}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTaiwan motorcycle API stopping.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
