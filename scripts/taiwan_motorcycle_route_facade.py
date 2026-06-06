from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import osmium

from script_utils import load_env_file
from valhalla_golden_routes import decode_polyline6, post_route


DEFAULT_BASE_URL = "http://localhost:8002"
DEFAULT_PBF = Path("infra/valhalla/custom_files/taiwan_custom.pbf")
DEFAULT_TWO_STAGE_PENALTY_SECONDS = 90.0


@dataclass(frozen=True)
class TaggedNode:
    osm_id: int
    lat: float
    lon: float


@dataclass(frozen=True)
class TaggedWay:
    osm_id: int
    name: str | None
    lane_pattern: str
    coordinates: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class MotorcycleSemanticIndex:
    two_stage_nodes: tuple[TaggedNode, ...]
    lane_ways: tuple[TaggedWay, ...]


def load_motorcycle_semantic_index(pbf_path: Path) -> MotorcycleSemanticIndex:
    two_stage_nodes: list[TaggedNode] = []
    lane_ways: list[TaggedWay] = []
    processor = (
        osmium.FileProcessor(str(pbf_path))
        .with_locations()
        .with_filter(
            osmium.filter.KeyFilter(
                "restriction:motorcycle",
                "tdx:motorcycle_waiting_zone",
                "motorcycle:lanes",
                "tdx:motorcycle_lane_restriction",
            )
        )
    )

    for obj in processor:
        tags = dict(obj.tags)
        object_type = type(obj).__name__
        if object_type == "Node" and (
            tags.get("restriction:motorcycle") == "two_stage_turn"
            or tags.get("tdx:motorcycle_waiting_zone") == "yes"
        ):
            if obj.location.valid():
                two_stage_nodes.append(
                    TaggedNode(
                        osm_id=int(obj.id),
                        lat=float(obj.lat),
                        lon=float(obj.lon),
                    )
                )
        elif object_type == "Way" and "motorcycle:lanes" in tags:
            coordinates = tuple(
                (float(node.lat), float(node.lon))
                for node in obj.nodes
                if node.location.valid()
            )
            if len(coordinates) >= 2:
                lane_ways.append(
                    TaggedWay(
                        osm_id=int(obj.id),
                        name=tags.get("name"),
                        lane_pattern=tags["motorcycle:lanes"],
                        coordinates=coordinates,
                    )
                )

    return MotorcycleSemanticIndex(
        two_stage_nodes=tuple(two_stage_nodes),
        lane_ways=tuple(lane_ways),
    )


def annotate_route(
    route: dict[str, Any],
    index: MotorcycleSemanticIndex,
    *,
    two_stage_threshold_m: float = 35.0,
    lane_threshold_m: float = 20.0,
    two_stage_penalty_seconds: float = DEFAULT_TWO_STAGE_PENALTY_SECONDS,
) -> dict[str, Any]:
    legs = route.get("trip", {}).get("legs")
    if not isinstance(legs, list):
        return route

    route.setdefault("taiwan_motorcycle", {})
    route["taiwan_motorcycle"].update(
        {
            "semantic_source": "pbf_proximity",
            "two_stage_turn_penalty_seconds": two_stage_penalty_seconds,
        }
    )

    for leg in legs:
        if not isinstance(leg, dict):
            continue
        shape = leg.get("shape")
        if not isinstance(shape, str) or not shape:
            continue
        points = decode_polyline6(shape)
        maneuvers = leg.get("maneuvers")
        if not isinstance(maneuvers, list):
            continue

        for maneuver in maneuvers:
            if not isinstance(maneuver, dict):
                continue
            semantic = _semantic_for_maneuver(
                maneuver,
                points,
                index,
                two_stage_threshold_m=two_stage_threshold_m,
                lane_threshold_m=lane_threshold_m,
                two_stage_penalty_seconds=two_stage_penalty_seconds,
            )
            if semantic:
                _merge_maneuver_semantics(maneuver, semantic)

    return route


def _semantic_for_maneuver(
    maneuver: dict[str, Any],
    points: list[tuple[float, float]],
    index: MotorcycleSemanticIndex,
    *,
    two_stage_threshold_m: float,
    lane_threshold_m: float,
    two_stage_penalty_seconds: float,
) -> dict[str, Any]:
    segment = _maneuver_segment(maneuver, points)
    if not segment:
        return {}

    semantic: dict[str, Any] = {}
    nearest_node = _nearest_two_stage_node(segment, index.two_stage_nodes)
    if nearest_node and nearest_node[1] <= two_stage_threshold_m:
        semantic.update(
            {
                "restriction:motorcycle": "two_stage_turn",
                "two_stage_turn": True,
                "two_stage_turn_penalty_seconds": two_stage_penalty_seconds,
                "two_stage_turn_source": "pbf_node_proximity",
                "two_stage_turn_osm_node_id": nearest_node[0].osm_id,
                "two_stage_turn_distance_m": round(nearest_node[1], 2),
            }
        )

    nearest_lane = _nearest_lane_way(segment, index.lane_ways, maneuver)
    if nearest_lane and nearest_lane[1] <= lane_threshold_m:
        way = nearest_lane[0]
        semantic.update(
            {
                "motorcycle:lanes": way.lane_pattern,
                "motorcycle_lanes_source": "pbf_way_proximity",
                "motorcycle_lanes_osm_way_id": way.osm_id,
                "motorcycle_lanes_distance_m": round(nearest_lane[1], 2),
            }
        )

    return semantic


def _merge_maneuver_semantics(maneuver: dict[str, Any], semantic: dict[str, Any]) -> None:
    custom = maneuver.get("custom")
    if not isinstance(custom, dict):
        custom = {}
        maneuver["custom"] = custom
    custom.update(semantic)

    taiwan = maneuver.get("taiwan_motorcycle")
    if not isinstance(taiwan, dict):
        taiwan = {}
        maneuver["taiwan_motorcycle"] = taiwan
    taiwan.update(semantic)

    if "restriction:motorcycle" in semantic:
        maneuver.setdefault("restriction:motorcycle", semantic["restriction:motorcycle"])
    if "motorcycle:lanes" in semantic:
        maneuver.setdefault("motorcycle:lanes", semantic["motorcycle:lanes"])


def _maneuver_segment(
    maneuver: dict[str, Any],
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not points:
        return []
    begin = _int_value(maneuver.get("begin_shape_index"))
    end = _int_value(maneuver.get("end_shape_index"))
    begin = max(0, min(begin, len(points) - 1))
    end = max(begin, min(end, len(points) - 1))
    return points[begin : end + 1]


def _nearest_two_stage_node(
    segment: list[tuple[float, float]],
    nodes: tuple[TaggedNode, ...],
) -> tuple[TaggedNode, float] | None:
    nearest: tuple[TaggedNode, float] | None = None
    for node in nodes:
        distance = min(_distance_meters(point, (node.lat, node.lon)) for point in segment)
        if nearest is None or distance < nearest[1]:
            nearest = (node, distance)
    return nearest


def _nearest_lane_way(
    segment: list[tuple[float, float]],
    ways: tuple[TaggedWay, ...],
    maneuver: dict[str, Any],
) -> tuple[TaggedWay, float] | None:
    maneuver_street_names = set(_maneuver_street_names(maneuver))
    nearest: tuple[TaggedWay, float] | None = None
    for way in ways:
        if way.name and maneuver_street_names and way.name not in maneuver_street_names:
            continue
        distance = min(
            _point_to_polyline_distance_m(point, way.coordinates)
            for point in segment
        )
        if nearest is None or distance < nearest[1]:
            nearest = (way, distance)
    return nearest


def _maneuver_street_names(maneuver: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for field in ("street_names", "begin_street_names"):
        raw_names = maneuver.get(field)
        if isinstance(raw_names, list):
            names.extend(str(name) for name in raw_names if str(name))
    return names


def _point_to_polyline_distance_m(
    point: tuple[float, float],
    polyline: tuple[tuple[float, float], ...],
) -> float:
    if not polyline:
        return math.inf
    if len(polyline) == 1:
        return _distance_meters(point, polyline[0])
    return min(
        _point_to_segment_distance_m(point, start, end)
        for start, end in zip(polyline, polyline[1:])
    )


def _point_to_segment_distance_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    px, py = _project(point, point)
    sx, sy = _project(start, point)
    ex, ey = _project(end, point)
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return math.hypot(px - sx, py - sy)
    t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (sx + t * dx), py - (sy + t * dy))


def _distance_meters(left: tuple[float, float], right: tuple[float, float]) -> float:
    left_x, left_y = _project(left, left)
    right_x, right_y = _project(right, left)
    return math.hypot(left_x - right_x, left_y - right_y)


def _project(point: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    lat, lon = point
    origin_lat, origin_lon = origin
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = 111_320.0 * math.cos(math.radians(origin_lat))
    return (
        (lon - origin_lon) * meters_per_degree_lon,
        (lat - origin_lat) * meters_per_degree_lat,
    )


def _int_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as payload_file:
        payload = json.load(payload_file)
    if not isinstance(payload, dict):
        raise ValueError("route payload must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Valhalla and enrich the route with Taiwan motorcycle semantics.")
    parser.add_argument("payload", type=Path, help="Valhalla /route JSON payload.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url", default=os.getenv("VALHALLA_URL", os.getenv("VALHALLA_BASE_URL", DEFAULT_BASE_URL)))
    parser.add_argument("--pbf", type=Path, default=Path(os.getenv("CUSTOM_PBF", DEFAULT_PBF)))
    parser.add_argument("--timeout-s", type=float, default=float(os.getenv("VALHALLA_TIMEOUT_S", "15")))
    parser.add_argument("--two-stage-threshold-m", type=float, default=float(os.getenv("TWO_STAGE_ANNOTATION_THRESHOLD_M", "35")))
    parser.add_argument("--lane-threshold-m", type=float, default=float(os.getenv("LANE_ANNOTATION_THRESHOLD_M", "20")))
    parser.add_argument("--two-stage-penalty-s", type=float, default=float(os.getenv("TWO_STAGE_TURN_PENALTY_SECONDS", "90")))
    return parser


def main() -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    args = build_parser().parse_args()
    if not args.pbf.exists():
        print(f"PBF does not exist: {args.pbf}", file=sys.stderr)
        return 2
    payload = load_payload(args.payload)
    response = post_route(args.base_url, payload, args.timeout_s)
    index = load_motorcycle_semantic_index(args.pbf)
    annotated = annotate_route(
        response,
        index,
        two_stage_threshold_m=args.two_stage_threshold_m,
        lane_threshold_m=args.lane_threshold_m,
        two_stage_penalty_seconds=args.two_stage_penalty_s,
    )
    print(json.dumps(annotated, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
