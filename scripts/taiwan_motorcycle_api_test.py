from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Any

import requests

from script_utils import load_env_file
from taiwan_motorcycle_api import TaiwanMotorcycleApi, create_server
from taiwan_motorcycle_route_facade import DEFAULT_PBF, load_payload


DEFAULT_BASE_URL = "http://localhost:8002"
DEFAULT_PAYLOAD = Path("infra/valhalla/custom_files/motorcycle_route_sample.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run live integration checks for the Taiwan motorcycle API facade.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--host", default=os.getenv("FACADE_TEST_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FACADE_TEST_PORT", "0")))
    parser.add_argument(
        "--base-url",
        default=os.getenv(
            "VALHALLA_URL",
            os.getenv("VALHALLA_BASE_URL", DEFAULT_BASE_URL),
        ),
    )
    parser.add_argument(
        "--pbf",
        type=Path,
        default=Path(os.getenv("CUSTOM_PBF", DEFAULT_PBF)),
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=Path(os.getenv("FACADE_PAYLOAD", DEFAULT_PAYLOAD)),
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("VALHALLA_TIMEOUT_S", "15")),
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
    )
    server = create_server(host=args.host, port=args.port, api=api)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://{args.host}:{server.server_address[1]}"
    try:
        _check_health(base_url, args.timeout_s)
        _check_route(base_url, args.payload, args.timeout_s)
        _check_trace_route(base_url, args.timeout_s)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(f"PASS facade integration: {base_url}")
    return 0


def _check_health(base_url: str, timeout_s: float) -> None:
    response = requests.get(f"{base_url}/health", timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    _assert(payload.get("status") == "ok", "health status should be ok")
    index = payload.get("semantic_index")
    _assert(isinstance(index, dict), "health response should include semantic_index")
    _assert(
        index.get("two_stage_nodes", 0) > 0,
        "semantic index should include two-stage nodes",
    )
    _assert(index.get("lane_ways", 0) > 0, "semantic index should include lane ways")


def _check_route(base_url: str, payload_path: Path, timeout_s: float) -> None:
    request_payload = load_payload(payload_path)
    response = requests.post(f"{base_url}/route", json=request_payload, timeout=timeout_s)
    response.raise_for_status()
    payload = response.json()
    _assert(
        isinstance(payload.get("taiwan_motorcycle"), dict),
        "route response should include taiwan_motorcycle",
    )

    maneuvers = _maneuvers(payload)
    _assert(maneuvers, "route response should include maneuvers")
    _assert(
        any("taiwan_motorcycle" in maneuver for maneuver in maneuvers),
        "at least one maneuver should include taiwan_motorcycle",
    )
    _assert(
        any("motorcycle:lanes" in maneuver for maneuver in maneuvers),
        "at least one maneuver should include motorcycle:lanes",
    )


def _check_trace_route(base_url: str, timeout_s: float) -> None:
    response = requests.post(
        f"{base_url}/trace_route",
        json={
            "shape": [
                {"lat": 25.0337, "lon": 121.5434},
                {"lat": 25.0329, "lon": 121.5410},
            ],
            "costing": "motorcycle",
            "shape_match": "map_snap",
            "directions_type": "instructions",
            "turn_lanes": True,
            "units": "kilometers",
        },
        timeout=timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    _assert(
        isinstance(payload.get("trip"), dict),
        "trace_route response should include trip",
    )


def _maneuvers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    maneuvers: list[dict[str, Any]] = []
    for leg in payload.get("trip", {}).get("legs", []):
        if not isinstance(leg, dict):
            continue
        for maneuver in leg.get("maneuvers", []):
            if isinstance(maneuver, dict):
                maneuvers.append(maneuver)
    return maneuvers


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL facade integration: {exc}", file=sys.stderr)
        sys.exit(1)
