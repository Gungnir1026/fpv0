from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

from script_utils import load_env_file


DEFAULT_CASES_PATH = Path("tests/golden_routes/daan_motorcycle_routes.json")
DEFAULT_BASE_URL = "http://localhost:8002"
DEFAULT_PRECISION = 6


def load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as case_file:
        payload = json.load(case_file)

    if isinstance(payload, dict):
        cases = payload.get("cases")
    else:
        cases = payload

    if not isinstance(cases, list) or not cases:
        raise ValueError("golden route cases must be a non-empty list")
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"case #{index} must be an object")
        if not case.get("name"):
            raise ValueError(f"case #{index} is missing name")
        if not isinstance(case.get("request"), dict):
            raise ValueError(f"case {case.get('name')} is missing request")
    return cases


def post_route(base_url: str, request_payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    response = requests.post(
        f"{base_url.rstrip('/')}/route",
        json=request_payload,
        timeout=timeout_s,
    )
    response.raise_for_status()
    return response.json()


def _route_summary(response_payload: dict[str, Any]) -> dict[str, Any]:
    return response_payload.get("trip", {}).get("summary", {})


def _maneuvers(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    maneuvers: list[dict[str, Any]] = []
    for leg in response_payload.get("trip", {}).get("legs", []):
        maneuvers.extend(leg.get("maneuvers", []))
    return maneuvers


def _maneuver_text(maneuvers: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for maneuver in maneuvers:
        for field in (
            "instruction",
            "verbal_transition_alert_instruction",
            "verbal_pre_transition_instruction",
            "verbal_post_transition_instruction",
        ):
            value = maneuver.get(field)
            if value:
                parts.append(str(value))
        for street_name in maneuver.get("street_names", []) or []:
            parts.append(str(street_name))
    return "\n".join(parts)


def _street_names(maneuvers: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for maneuver in maneuvers:
        for field in ("street_names", "begin_street_names"):
            raw_names = maneuver.get(field)
            if isinstance(raw_names, list):
                names.update(str(name) for name in raw_names if str(name))
    return names


def decode_polyline6(encoded: str, precision: int = DEFAULT_PRECISION) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    index = 0
    latitude = 0
    longitude = 0
    factor = float(10**precision)

    while index < len(encoded):
        lat_delta, index = _decode_polyline_value(encoded, index)
        lon_delta, index = _decode_polyline_value(encoded, index)
        latitude += lat_delta
        longitude += lon_delta
        coordinates.append((latitude / factor, longitude / factor))

    return coordinates


def _decode_polyline_value(encoded: str, start_index: int) -> tuple[int, int]:
    if start_index >= len(encoded):
        raise ValueError("polyline data is incomplete")

    index = start_index
    shift = 0
    result = 0
    while True:
        if index >= len(encoded):
            raise ValueError("polyline data is incomplete")
        byte = ord(encoded[index]) - 63
        index += 1
        if byte < 0 or byte > 0x3F:
            raise ValueError("polyline contains an invalid character")
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            break

    delta = ~(result >> 1) if result & 1 else result >> 1
    return delta, index


def _route_points(response_payload: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for leg in response_payload.get("trip", {}).get("legs", []):
        if not isinstance(leg, dict):
            continue
        shape = leg.get("shape")
        if not isinstance(shape, str) or not shape:
            continue
        leg_points = decode_polyline6(shape)
        if points and leg_points and points[-1] == leg_points[0]:
            points.extend(leg_points[1:])
        else:
            points.extend(leg_points)
    return points


def _point_in_bbox(point: tuple[float, float], bbox: dict[str, Any]) -> bool:
    lat, lon = point
    return (
        float(bbox["min_lat"]) <= lat <= float(bbox["max_lat"])
        and float(bbox["min_lon"]) <= lon <= float(bbox["max_lon"])
    )


def _bbox_label(bbox: dict[str, Any]) -> str:
    return str(bbox.get("name") or bbox.get("label") or bbox)


def _validate_numeric_range(
    failures: list[str],
    label: str,
    value: Any,
    expected: dict[str, Any],
) -> None:
    if value is None:
        failures.append(f"{label} is missing")
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        failures.append(f"{label} is not numeric: {value!r}")
        return

    minimum = expected.get("min")
    maximum = expected.get("max")
    if minimum is not None and number < float(minimum):
        failures.append(f"{label} {number:.3f} is below minimum {minimum}")
    if maximum is not None and number > float(maximum):
        failures.append(f"{label} {number:.3f} is above maximum {maximum}")


def _validate_summary_bbox(
    failures: list[str],
    summary: dict[str, Any],
    expected_bbox: dict[str, Any],
) -> None:
    tolerance = float(expected_bbox.get("tolerance_degrees", 0.0))
    comparisons = (
        ("min_lon", "min_lon", -tolerance),
        ("min_lat", "min_lat", -tolerance),
        ("max_lon", "max_lon", tolerance),
        ("max_lat", "max_lat", tolerance),
    )
    for summary_key, expected_key, offset in comparisons:
        if expected_key not in expected_bbox:
            continue
        value = summary.get(summary_key)
        if value is None:
            failures.append(f"summary {summary_key} is missing")
            continue
        expected_value = float(expected_bbox[expected_key])
        number = float(value)
        if offset < 0 and number < expected_value + offset:
            failures.append(f"summary {summary_key} {number:.6f} is outside expected bbox")
        if offset > 0 and number > expected_value + offset:
            failures.append(f"summary {summary_key} {number:.6f} is outside expected bbox")


def validate_case_result(case: dict[str, Any], response_payload: dict[str, Any]) -> list[str]:
    expected = case.get("expect", {})
    failures: list[str] = []
    status = response_payload.get("status", response_payload.get("trip", {}).get("status"))
    expected_status = expected.get("status", 0)
    if status != expected_status:
        failures.append(f"status {status!r} does not match expected {expected_status!r}")

    summary = _route_summary(response_payload)
    if "length_km" in expected:
        _validate_numeric_range(failures, "length_km", summary.get("length"), expected["length_km"])
    if "time_s" in expected:
        _validate_numeric_range(failures, "time_s", summary.get("time"), expected["time_s"])
    if "cost" in expected:
        _validate_numeric_range(failures, "cost", summary.get("cost"), expected["cost"])
    if "summary_bbox" in expected:
        _validate_summary_bbox(failures, summary, expected["summary_bbox"])

    maneuvers = _maneuvers(response_payload)
    min_maneuvers = expected.get("min_maneuvers")
    if min_maneuvers is not None and len(maneuvers) < int(min_maneuvers):
        failures.append(f"maneuver count {len(maneuvers)} is below minimum {min_maneuvers}")

    required_travel_type = expected.get("travel_type")
    if required_travel_type:
        invalid_types = {
            maneuver.get("travel_type")
            for maneuver in maneuvers
            if maneuver.get("travel_type") != required_travel_type
        }
        if invalid_types:
            failures.append(f"unexpected travel_type values: {sorted(invalid_types)}")

    text = _maneuver_text(maneuvers)
    street_names = _street_names(maneuvers)
    for required in expected.get("required_substrings", []):
        if required not in text:
            failures.append(f"required substring not found: {required}")
    for forbidden in expected.get("forbidden_substrings", []):
        if forbidden in text:
            failures.append(f"forbidden substring found: {forbidden}")

    for required in expected.get("required_street_names", []):
        if required not in street_names:
            failures.append(f"required street name not found: {required}")
    for avoided in expected.get("avoided_street_names", []):
        if avoided in street_names or avoided in text:
            failures.append(f"avoided street name found: {avoided}")

    maneuver_types = [maneuver.get("type") for maneuver in maneuvers]
    for required_type in expected.get("required_maneuver_types", []):
        if required_type not in maneuver_types:
            failures.append(f"required maneuver type not found: {required_type}")
    for avoided_type in expected.get("avoided_maneuver_types", []):
        if avoided_type in maneuver_types:
            failures.append(f"avoided maneuver type found: {avoided_type}")

    if expected.get("required_shape_bboxes") or expected.get("avoided_shape_bboxes"):
        try:
            points = _route_points(response_payload)
        except ValueError as exc:
            failures.append(f"route shape could not be decoded: {exc}")
            points = []

        for bbox in expected.get("required_shape_bboxes", []):
            if not any(_point_in_bbox(point, bbox) for point in points):
                failures.append(f"route does not pass required bbox: {_bbox_label(bbox)}")
        for bbox in expected.get("avoided_shape_bboxes", []):
            if any(_point_in_bbox(point, bbox) for point in points):
                failures.append(f"route passes avoided bbox: {_bbox_label(bbox)}")

    return failures


def build_parser(
    *,
    default_cases_path: Path = DEFAULT_CASES_PATH,
    default_cases_env: str = "GOLDEN_ROUTES",
    description: str = "Run Valhalla route golden cases.",
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    cases_default = os.getenv(default_cases_env, str(default_cases_path))
    parser.add_argument("--cases", type=Path, default=Path(cases_default))
    parser.add_argument(
        "--base-url",
        default=os.getenv("VALHALLA_URL", os.getenv("VALHALLA_BASE_URL", DEFAULT_BASE_URL)),
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=float(os.getenv("VALHALLA_TIMEOUT_S", "15")),
    )
    return parser


def run_cli(
    *,
    default_cases_path: Path = DEFAULT_CASES_PATH,
    default_cases_env: str = "GOLDEN_ROUTES",
    description: str = "Run Valhalla route golden cases.",
) -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    args = build_parser(
        default_cases_path=default_cases_path,
        default_cases_env=default_cases_env,
        description=description,
    ).parse_args()
    cases = load_cases(args.cases)

    failed = False
    for case in cases:
        response_payload = post_route(args.base_url, case["request"], args.timeout_s)
        failures = validate_case_result(case, response_payload)
        summary = _route_summary(response_payload)
        maneuvers = _maneuvers(response_payload)
        name = case["name"]
        if failures:
            failed = True
            print(f"FAIL {name}")
            for failure in failures:
                print(f"  - {failure}")
            continue

        print(
            "PASS "
            f"{name}: {summary.get('length', 0):.3f} km, "
            f"{summary.get('time', 0):.1f} s, "
            f"{len(maneuvers)} maneuvers"
        )

    return 1 if failed else 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
