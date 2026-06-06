from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pbf_tag_audit import PbfTagCounts, evaluate_minimums


class PbfTagAuditTests(unittest.TestCase):
    def test_accepts_counts_above_minimums(self) -> None:
        counts = PbfTagCounts(
            two_stage_nodes=10,
            waiting_zone_nodes=10,
            motorcycle_lane_ways=5,
            lane_restriction_ways=5,
            motorcycle_blocked_ways=1,
        )

        failures = evaluate_minimums(
            counts,
            {
                "two_stage_nodes": 1,
                "waiting_zone_nodes": 1,
                "motorcycle_lane_ways": 1,
                "lane_restriction_ways": 1,
                "motorcycle_blocked_ways": 0,
            },
        )

        self.assertEqual(failures, [])

    def test_reports_missing_required_tags(self) -> None:
        counts = PbfTagCounts(two_stage_nodes=0, motorcycle_lane_ways=0)

        failures = evaluate_minimums(
            counts,
            {
                "two_stage_nodes": 1,
                "motorcycle_lane_ways": 1,
            },
        )

        self.assertEqual(len(failures), 2)
        self.assertTrue(any("two_stage_nodes" in failure for failure in failures))
        self.assertTrue(any("motorcycle_lane_ways" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
