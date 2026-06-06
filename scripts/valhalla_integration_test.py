from __future__ import annotations

import sys
from pathlib import Path

from valhalla_golden_routes import run_cli


DEFAULT_CASES_PATH = Path("tests/integration/valhalla_motorcycle_semantics.json")


def main() -> int:
    return run_cli(
        default_cases_path=DEFAULT_CASES_PATH,
        default_cases_env="INTEGRATION_ROUTES",
        description="Run Valhalla integration cases for Taiwan motorcycle semantics.",
    )


if __name__ == "__main__":
    sys.exit(main())
