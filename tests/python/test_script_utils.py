from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from osm_tdx_fusion import normalize_lane_pattern, should_block_motorcycle_access
from script_utils import load_env_file, parse_bbox
from taipei_open_data_ingest import split_intersection_roads


class LoadEnvFileTests(unittest.TestCase):
    def test_loads_entries_without_overwriting_exported_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "# comment\n"
                "EXPORTED_VALUE=from_file\n"
                "NEW_VALUE='trimmed value'\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"EXPORTED_VALUE": "from_shell"},
                clear=True,
            ):
                load_env_file(env_file)
                self.assertEqual(os.environ["EXPORTED_VALUE"], "from_shell")
                self.assertEqual(os.environ["NEW_VALUE"], "trimmed value")


class ParseBboxTests(unittest.TestCase):
    def test_parses_valid_bbox(self) -> None:
        self.assertEqual(
            parse_bbox("121.5150,25.0150,121.5650,25.0500"),
            (121.515, 25.015, 121.565, 25.05),
        )

    def test_returns_none_for_blank_bbox(self) -> None:
        self.assertIsNone(parse_bbox(""))

    def test_rejects_non_numeric_bbox(self) -> None:
        with self.assertRaisesRegex(ValueError, "numeric"):
            parse_bbox("west,25.0150,121.5650,25.0500")

    def test_rejects_reversed_bbox(self) -> None:
        with self.assertRaisesRegex(ValueError, "smaller"):
            parse_bbox("121.5650,25.0150,121.5150,25.0500")


class DataNormalizationTests(unittest.TestCase):
    def test_splits_taipei_intersection_roads(self) -> None:
        self.assertEqual(
            split_intersection_roads("信義路三段與復興南路二段"),
            ["信義路三段", "復興南路二段"],
        )

    def test_preserves_valid_lane_pattern(self) -> None:
        self.assertEqual(normalize_lane_pattern("no | yes | yes", "no|yes"), "no|yes|yes")

    def test_blocks_motorcycles_when_every_lane_is_closed(self) -> None:
        self.assertTrue(should_block_motorcycle_access("no|no", None))
        self.assertFalse(should_block_motorcycle_access("no|yes", None))


if __name__ == "__main__":
    unittest.main()
