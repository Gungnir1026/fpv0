from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import osmium


DEFAULT_PBF = Path("infra/valhalla/custom_files/taiwan_custom.pbf")


@dataclass
class PbfTagCounts:
    scan_completed: bool = True
    tagged_nodes_checked: int = 0
    tagged_ways_checked: int = 0
    two_stage_nodes: int = 0
    waiting_zone_nodes: int = 0
    motorcycle_lane_ways: int = 0
    lane_restriction_ways: int = 0
    motorcycle_blocked_ways: int = 0
    samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _sample_tags(tags: dict[str, str]) -> dict[str, str]:
    interesting_keys = (
        "name",
        "highway",
        "restriction:motorcycle",
        "tdx:motorcycle_waiting_zone",
        "motorcycle:lanes",
        "tdx:motorcycle_lane_restriction",
        "motorcycle",
    )
    return {key: tags[key] for key in interesting_keys if key in tags}


def _append_sample(
    samples: dict[str, list[dict[str, Any]]],
    sample_key: str,
    sample: dict[str, Any],
    sample_limit: int,
) -> None:
    bucket = samples.setdefault(sample_key, [])
    if len(bucket) < sample_limit:
        bucket.append(sample)


def _minimums_met(counts: PbfTagCounts, minimums: dict[str, int]) -> bool:
    return all(getattr(counts, field_name) >= minimum for field_name, minimum in minimums.items())


def audit_pbf(
    path: Path,
    sample_limit: int,
    minimums: dict[str, int] | None = None,
    full_scan: bool = True,
) -> PbfTagCounts:
    counts = PbfTagCounts()
    minimums = minimums or {}
    keys = (
        "restriction:motorcycle",
        "tdx:motorcycle_waiting_zone",
        "motorcycle:lanes",
        "tdx:motorcycle_lane_restriction",
        "motorcycle",
    )
    processor = osmium.FileProcessor(str(path)).with_filter(osmium.filter.KeyFilter(*keys))

    for obj in processor:
        object_type = type(obj).__name__
        tags = dict(obj.tags)

        if object_type == "Node":
            counts.tagged_nodes_checked += 1
            is_two_stage = tags.get("restriction:motorcycle") == "two_stage_turn"
            is_waiting_zone = tags.get("tdx:motorcycle_waiting_zone") == "yes"
            if is_two_stage:
                counts.two_stage_nodes += 1
            if is_waiting_zone:
                counts.waiting_zone_nodes += 1
            if is_two_stage or is_waiting_zone:
                sample: dict[str, Any] = {
                    "type": "node",
                    "id": obj.id,
                    "tags": _sample_tags(tags),
                }
                if obj.location.valid():
                    sample["lat"] = float(obj.lat)
                    sample["lon"] = float(obj.lon)
                if is_two_stage:
                    _append_sample(counts.samples, "two_stage_nodes", sample, sample_limit)
                if is_waiting_zone:
                    _append_sample(counts.samples, "waiting_zone_nodes", sample, sample_limit)

        elif object_type == "Way":
            counts.tagged_ways_checked += 1
            has_lane_pattern = "motorcycle:lanes" in tags
            has_lane_restriction = tags.get("tdx:motorcycle_lane_restriction") == "yes"
            blocks_motorcycles = tags.get("motorcycle") == "no"

            if has_lane_pattern:
                counts.motorcycle_lane_ways += 1
            if has_lane_restriction:
                counts.lane_restriction_ways += 1
            if blocks_motorcycles:
                counts.motorcycle_blocked_ways += 1

            if has_lane_pattern or has_lane_restriction or blocks_motorcycles:
                sample = {
                    "type": "way",
                    "id": obj.id,
                    "tags": _sample_tags(tags),
                }
                if has_lane_pattern:
                    _append_sample(counts.samples, "motorcycle_lane_ways", sample, sample_limit)
                if has_lane_restriction:
                    _append_sample(counts.samples, "lane_restriction_ways", sample, sample_limit)
                if blocks_motorcycles:
                    _append_sample(counts.samples, "motorcycle_blocked_ways", sample, sample_limit)

        if not full_scan and _minimums_met(counts, minimums):
            counts.scan_completed = False
            break

    return counts


def evaluate_minimums(counts: PbfTagCounts, minimums: dict[str, int]) -> list[str]:
    failures: list[str] = []
    for field_name, minimum in minimums.items():
        value = getattr(counts, field_name)
        if value < minimum:
            failures.append(f"{field_name}={value} is below required minimum {minimum}")
    return failures


def print_text_report(path: Path, counts: PbfTagCounts, failures: list[str]) -> None:
    print(f"PBF tag audit: {path}")
    print(f"scan_completed: {counts.scan_completed}")
    if not counts.scan_completed:
        print("scan_note: stopped after all minimum checks were satisfied; counts are lower bounds")
    print(f"tagged_nodes_checked: {counts.tagged_nodes_checked}")
    print(f"tagged_ways_checked: {counts.tagged_ways_checked}")
    print(f"two_stage_nodes: {counts.two_stage_nodes}")
    print(f"waiting_zone_nodes: {counts.waiting_zone_nodes}")
    print(f"motorcycle_lane_ways: {counts.motorcycle_lane_ways}")
    print(f"lane_restriction_ways: {counts.lane_restriction_ways}")
    print(f"motorcycle_blocked_ways: {counts.motorcycle_blocked_ways}")

    if counts.samples:
        print("samples:")
        for sample_key, samples in counts.samples.items():
            print(f"  {sample_key}:")
            for sample in samples:
                label = f"{sample['type']} {sample['id']}"
                if "lat" in sample and "lon" in sample:
                    label += f" ({sample['lat']:.6f}, {sample['lon']:.6f})"
                print(f"    - {label} {sample['tags']}")

    if failures:
        print("failures:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("minimum checks: PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Taiwan motorcycle tags in a fused OSM PBF.")
    parser.add_argument("--pbf", type=Path, default=Path(os.getenv("CUSTOM_PBF", DEFAULT_PBF)))
    parser.add_argument("--sample-limit", type=int, default=int(os.getenv("PBF_AUDIT_SAMPLE_LIMIT", "5")))
    parser.add_argument("--min-two-stage-nodes", type=int, default=int(os.getenv("MIN_TWO_STAGE_NODES", "1")))
    parser.add_argument("--min-waiting-zone-nodes", type=int, default=int(os.getenv("MIN_WAITING_ZONE_NODES", "1")))
    parser.add_argument("--min-motorcycle-lane-ways", type=int, default=int(os.getenv("MIN_MOTORCYCLE_LANE_WAYS", "1")))
    parser.add_argument("--min-lane-restriction-ways", type=int, default=int(os.getenv("MIN_LANE_RESTRICTION_WAYS", "1")))
    parser.add_argument("--min-motorcycle-blocked-ways", type=int, default=int(os.getenv("MIN_MOTORCYCLE_BLOCKED_WAYS", "0")))
    parser.add_argument("--full-scan", action="store_true", help="Scan the whole PBF and report exact counts.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.pbf.exists():
        print(f"PBF does not exist: {args.pbf}", file=sys.stderr)
        return 2

    minimums = {
        "two_stage_nodes": args.min_two_stage_nodes,
        "waiting_zone_nodes": args.min_waiting_zone_nodes,
        "motorcycle_lane_ways": args.min_motorcycle_lane_ways,
        "lane_restriction_ways": args.min_lane_restriction_ways,
        "motorcycle_blocked_ways": args.min_motorcycle_blocked_ways,
    }
    counts = audit_pbf(
        args.pbf,
        sample_limit=args.sample_limit,
        minimums=minimums,
        full_scan=args.full_scan,
    )
    failures = evaluate_minimums(counts, minimums)

    if args.json:
        print(
            json.dumps(
                {
                    "pbf": str(args.pbf),
                    "counts": asdict(counts),
                    "failures": failures,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_text_report(args.pbf, counts, failures)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
