from __future__ import annotations

import os
from pathlib import Path


BBox = tuple[float, float, float, float]


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting exported variables."""
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def parse_bbox(raw: str | None) -> BBox | None:
    """Parse min_lon,min_lat,max_lon,max_lat into a validated bounding box."""
    if not raw:
        return None

    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be min_lon,min_lat,max_lon,max_lat")

    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in parts)
    except ValueError as exc:
        raise ValueError("bbox values must be numeric") from exc

    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError("bbox min values must be smaller than max values")
    return min_lon, min_lat, max_lon, max_lat
