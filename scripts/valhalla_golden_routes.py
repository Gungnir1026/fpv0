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
    for required in expected.get("required_substrings", []):
        if required not in text:
            failures.append(f"required substring not found: {required}")
    for forbidden in expected.get("forbidden_substrings", []):
        if forbidden in text:
            failures.append(f"forbidden substring found: {forbidden}")

    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Valhalla route golden cases.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--cases", type=Path, default=Path(os.getenv("GOLDEN_ROUTES", DEFAULT_CASES_PATH)))
    parser.add_argument("--base-url", default=os.getenv("VALHALLA_URL", os.getenv("VALHALLA_BASE_URL", DEFAULT_BASE_URL)))
    parser.add_argument("--timeout-s", type=float, default=float(os.getenv("VALHALLA_TIMEOUT_S", "15")))
    return parser


def main() -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    args = build_parser().parse_args()
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


if __name__ == "__main__":
    sys.exit(main())
