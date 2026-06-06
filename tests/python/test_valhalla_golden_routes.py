from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from valhalla_golden_routes import build_parser, decode_polyline6, load_cases, validate_case_result


SAMPLE_RESPONSE = {
    "status": 0,
    "trip": {
        "summary": {
            "length": 2.1,
            "time": 340.0,
            "cost": 590.0,
            "min_lat": 25.033,
            "min_lon": 121.532,
            "max_lat": 25.038,
            "max_lon": 121.544,
        },
        "legs": [
            {
                "maneuvers": [
                    {
                        "type": 1,
                        "instruction": "Drive south on 復興南路一段.",
                        "street_names": ["復興南路一段"],
                        "travel_type": "motorcycle",
                    },
                    {
                        "type": 15,
                        "instruction": "Turn left onto 仁愛路三段.",
                        "street_names": ["仁愛路三段"],
                        "travel_type": "motorcycle",
                    },
                ]
            }
        ],
    },
}


class GoldenRouteValidationTests(unittest.TestCase):
    def test_accepts_matching_route_response(self) -> None:
        case = {
            "name": "sample",
            "expect": {
                "status": 0,
                "length_km": {"min": 2.0, "max": 2.2},
                "time_s": {"min": 300, "max": 360},
                "min_maneuvers": 2,
                "travel_type": "motorcycle",
                "required_substrings": ["復興南路一段", "仁愛路三段"],
                "summary_bbox": {
                    "min_lon": 121.531,
                    "min_lat": 25.032,
                    "max_lon": 121.545,
                    "max_lat": 25.039,
                    "tolerance_degrees": 0.002,
                },
            },
        }

        self.assertEqual(validate_case_result(case, SAMPLE_RESPONSE), [])

    def test_reports_route_regressions(self) -> None:
        case = {
            "name": "sample",
            "expect": {
                "status": 0,
                "length_km": {"min": 3.0, "max": 4.0},
                "required_substrings": ["不存在的道路"],
                "forbidden_substrings": ["仁愛路三段"],
            },
        }

        failures = validate_case_result(case, SAMPLE_RESPONSE)

        self.assertTrue(any("length_km" in failure for failure in failures))
        self.assertTrue(any("required substring" in failure for failure in failures))
        self.assertTrue(any("forbidden substring" in failure for failure in failures))

    def test_validates_street_names_maneuver_types_and_shape_bboxes(self) -> None:
        case = {
            "name": "sample",
            "expect": {
                "required_street_names": ["復興南路一段"],
                "avoided_street_names": ["民族陸橋"],
                "required_maneuver_types": [1],
                "avoided_maneuver_types": [13],
                "required_shape_bboxes": [
                    {
                        "name": "origin",
                        "min_lat": -0.001,
                        "min_lon": -0.001,
                        "max_lat": 0.001,
                        "max_lon": 0.001,
                    }
                ],
                "avoided_shape_bboxes": [
                    {
                        "name": "far-away",
                        "min_lat": 10,
                        "min_lon": 10,
                        "max_lat": 11,
                        "max_lon": 11,
                    }
                ],
            },
        }
        response = {
            **SAMPLE_RESPONSE,
            "trip": {
                **SAMPLE_RESPONSE["trip"],
                "legs": [
                    {
                        "shape": "??AA",
                        "maneuvers": SAMPLE_RESPONSE["trip"]["legs"][0]["maneuvers"],
                    }
                ],
            },
        }

        self.assertEqual(validate_case_result(case, response), [])

    def test_decodes_polyline6(self) -> None:
        self.assertEqual(decode_polyline6("??AA"), [(0.0, 0.0), (0.000001, 0.000001)])

    def test_loads_committed_golden_cases(self) -> None:
        cases = load_cases(ROOT_DIR / "tests/golden_routes/daan_motorcycle_routes.json")

        self.assertGreaterEqual(len(cases), 3)
        self.assertTrue(all(case["request"]["costing"] == "motorcycle" for case in cases))

    def test_build_parser_uses_custom_cases_environment_variable(self) -> None:
        with patch.dict(
            "os.environ",
            {"INTEGRATION_ROUTES": "custom/integration.json"},
            clear=False,
        ):
            parser = build_parser(
                default_cases_path=Path("tests/integration/default.json"),
                default_cases_env="INTEGRATION_ROUTES",
            )

        args = parser.parse_args([])

        self.assertEqual(args.cases, Path("custom/integration.json"))


if __name__ == "__main__":
    unittest.main()
