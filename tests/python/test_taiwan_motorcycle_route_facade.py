from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from taiwan_motorcycle_route_facade import (
    MotorcycleSemanticIndex,
    TaggedNode,
    TaggedWay,
    annotate_route,
)


class TaiwanMotorcycleRouteFacadeTests(unittest.TestCase):
    def test_annotates_two_stage_turn_and_motorcycle_lanes(self) -> None:
        route = {
            "trip": {
                "legs": [
                    {
                        "shape": "??_ibE?",
                        "maneuvers": [
                            {
                                "type": 15,
                                "instruction": "Turn left onto Test Road.",
                                "begin_shape_index": 0,
                                "end_shape_index": 1,
                                "street_names": ["Test Road"],
                            }
                        ],
                    }
                ]
            }
        }
        index = MotorcycleSemanticIndex(
            two_stage_nodes=(
                TaggedNode(osm_id=10, lat=0.0001, lon=0.0),
            ),
            lane_ways=(
                TaggedWay(
                    osm_id=20,
                    name="Test Road",
                    lane_pattern="no|yes",
                    coordinates=((0.0, 0.0), (0.0001, 0.0)),
                ),
            ),
        )

        annotated = annotate_route(copy.deepcopy(route), index)
        maneuver = annotated["trip"]["legs"][0]["maneuvers"][0]

        self.assertEqual(maneuver["restriction:motorcycle"], "two_stage_turn")
        self.assertEqual(maneuver["motorcycle:lanes"], "no|yes")
        self.assertTrue(maneuver["taiwan_motorcycle"]["two_stage_turn"])
        self.assertEqual(
            maneuver["taiwan_motorcycle"]["two_stage_turn_penalty_seconds"],
            90.0,
        )
        self.assertEqual(maneuver["custom"]["motorcycle:lanes"], "no|yes")

    def test_leaves_route_unchanged_when_no_semantics_match(self) -> None:
        route = {
            "trip": {
                "legs": [
                    {
                        "shape": "??AA",
                        "maneuvers": [
                            {
                                "type": 2,
                                "begin_shape_index": 0,
                                "end_shape_index": 1,
                            }
                        ],
                    }
                ]
            }
        }
        index = MotorcycleSemanticIndex(two_stage_nodes=(), lane_ways=())

        annotated = annotate_route(copy.deepcopy(route), index)

        self.assertNotIn("custom", annotated["trip"]["legs"][0]["maneuvers"][0])


if __name__ == "__main__":
    unittest.main()
