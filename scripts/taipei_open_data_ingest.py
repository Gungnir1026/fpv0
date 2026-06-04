from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
import requests
from psycopg2.extras import Json
from script_utils import load_env_file


LOGGER = logging.getLogger("taipei_open_data_ingest")

DEFAULT_DATABASE_URL = "postgresql://tw_nav:tw_nav_dev_password@localhost:5432/tw_nav"
DEFAULT_CITY = "臺北市"
DEFAULT_DISTRICT = "大安區"

DEFAULT_TWO_STAGE_TURN_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download"
    "?rid=86c7c859-78d4-430c-bada-277203abd881"
)
DEFAULT_DIRECT_LEFT_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download"
    "?rid=e77ab72d-cffa-46be-8b5c-16d60c32fce5"
)
DEFAULT_OPEN_THIRD_LANE_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download"
    "?rid=a15f2a8d-eb1a-489d-a25f-3d816af10177"
)
DEFAULT_MOTORCYCLE_BAN_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download"
    "?rid=2c833533-071f-4b3c-9d17-39662d805b66"
)

ROAD_NAME_RE = re.compile(
    r"[\u4e00-\u9fff0-9]{1,14}(?:大道|快速道路|路|街|巷|橋|匝道)"
    r"(?:[一二三四五六七八九十0-9]+段)?"
)


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def fetch_csv(session: requests.Session, url: str, raw_dir: Path, dataset: str) -> list[dict[str, str]]:
    LOGGER.info("Fetching %s from %s", dataset, url)
    response = session.get(url, timeout=60)
    response.raise_for_status()

    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{dataset}.csv"
    raw_file.write_bytes(response.content)

    text = decode_csv(response.content)
    reader = csv.DictReader(io.StringIO(text))
    return [
        {str(key).strip(): (value or "").strip() for key, value in row.items() if key is not None}
        for row in reader
    ]


def normalized_key(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def pick(row: dict[str, str], candidates: tuple[str, ...]) -> str:
    for candidate in candidates:
        if row.get(candidate):
            return row[candidate]

    normalized_candidates = {normalized_key(candidate) for candidate in candidates}
    for key, value in row.items():
        if normalized_key(key) in normalized_candidates and value:
            return value
    return ""


def source_id(dataset: str, row: dict[str, str]) -> str:
    direct = pick(row, ("編號", "序號", "id", "ID"))
    if direct:
        return f"{dataset}:{direct}"
    stable = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return f"{dataset}:{hashlib.sha256(stable.encode('utf-8')).hexdigest()}"


def split_intersection_roads(value: str) -> list[str]:
    if not value:
        return []

    normalized = (
        value.replace("臺", "台")
        .replace("／", "/")
        .replace("、", "/")
        .replace("，", "/")
        .replace(",", "/")
        .replace("與", "/")
        .replace("及", "/")
        .replace("至", "/")
    )
    roads: list[str] = []
    for part in normalized.split("/"):
        for match in ROAD_NAME_RE.findall(part):
            road = match.replace("台", "臺")
            if road not in roads:
                roads.append(road)
    return roads


def district_value(row: dict[str, str]) -> str:
    return pick(row, ("行政區", "分區", "區域", "區"))


def row_in_scope(row: dict[str, str], district: str | None) -> bool:
    if not district:
        return True

    value = district_value(row)
    return not value or district in value or value in district


def record_ingest_run(
    conn: psycopg2.extensions.connection,
    dataset: str,
    endpoint: str,
    row_count: int,
    started_at: datetime,
    metadata: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_tdx.ingest_runs
                (dataset, source_endpoint, row_count, started_at, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (dataset, endpoint, row_count, started_at, Json(metadata)),
        )


def insert_waiting_zone(
    conn: psycopg2.extensions.connection,
    endpoint: str,
    dataset: str,
    row: dict[str, str],
    city: str,
) -> None:
    intersection = pick(row, ("路口", "交叉路口", "地點", "位置"))
    roads = split_intersection_roads(intersection)
    raw = dict(row)
    raw["roads"] = roads
    raw["source_dataset"] = dataset
    raw["restriction:motorcycle"] = "two_stage_turn"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_tdx.motorcycle_waiting_zones
                (
                    source_endpoint, source_id, city, district, name, road_name,
                    direction, raw, geom
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (source_endpoint, source_id) DO UPDATE SET
                city = EXCLUDED.city,
                district = EXCLUDED.district,
                name = EXCLUDED.name,
                road_name = EXCLUDED.road_name,
                direction = EXCLUDED.direction,
                raw = EXCLUDED.raw,
                geom = EXCLUDED.geom,
                fetched_at = now()
            """,
            (
                endpoint,
                source_id(dataset, row),
                city,
                district_value(row),
                intersection,
                "|".join(roads) if roads else intersection,
                pick(row, ("方向", "車行方向")),
                Json(raw),
            ),
        )


def insert_lane_restriction(
    conn: psycopg2.extensions.connection,
    endpoint: str,
    dataset: str,
    row: dict[str, str],
    city: str,
    lane_pattern: str,
    restriction_type: str,
) -> None:
    road_name = pick(row, ("路名", "路段", "道路", "道路名稱"))
    roads = split_intersection_roads(road_name)
    raw = dict(row)
    raw["roads"] = roads
    raw["source_dataset"] = dataset
    raw["motorcycle:lanes"] = lane_pattern
    raw["restriction_type"] = restriction_type

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw_tdx.motorcycle_lane_restrictions
                (
                    source_endpoint, source_id, city, district, road_name,
                    direction, lane_pattern, restriction_type, raw, geom
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            ON CONFLICT (source_endpoint, source_id) DO UPDATE SET
                city = EXCLUDED.city,
                district = EXCLUDED.district,
                road_name = EXCLUDED.road_name,
                direction = EXCLUDED.direction,
                lane_pattern = EXCLUDED.lane_pattern,
                restriction_type = EXCLUDED.restriction_type,
                raw = EXCLUDED.raw,
                geom = EXCLUDED.geom,
                fetched_at = now()
            """,
            (
                endpoint,
                source_id(dataset, row),
                city,
                district_value(row),
                road_name,
                pick(row, ("方向", "車行方向")),
                lane_pattern,
                restriction_type,
                Json(raw),
            ),
        )


def ingest_two_stage_turns(
    conn: psycopg2.extensions.connection,
    session: requests.Session,
    args: argparse.Namespace,
) -> int:
    rows = fetch_csv(session, args.two_stage_turn_url, args.raw_dir, "taipei_two_stage_turns")
    inserted = 0
    for row in rows:
        if not row_in_scope(row, args.district):
            continue
        insert_waiting_zone(
            conn,
            args.two_stage_turn_url,
            "taipei_two_stage_turns",
            row,
            args.city,
        )
        inserted += 1
    return inserted


def ingest_motorcycle_bans(
    conn: psycopg2.extensions.connection,
    session: requests.Session,
    args: argparse.Namespace,
) -> int:
    rows = fetch_csv(session, args.motorcycle_ban_url, args.raw_dir, "taipei_motorcycle_bans")
    inserted = 0
    for row in rows:
        if not row_in_scope(row, args.district):
            continue
        insert_lane_restriction(
            conn,
            args.motorcycle_ban_url,
            "taipei_motorcycle_bans",
            row,
            args.city,
            lane_pattern="no",
            restriction_type="motorcycle=no",
        )
        inserted += 1
    return inserted


def ingest_open_third_lanes(
    conn: psycopg2.extensions.connection,
    session: requests.Session,
    args: argparse.Namespace,
) -> int:
    rows = fetch_csv(session, args.open_third_lane_url, args.raw_dir, "taipei_open_third_lanes")
    inserted = 0
    for row in rows:
        if not row_in_scope(row, args.district):
            continue
        insert_lane_restriction(
            conn,
            args.open_third_lane_url,
            "taipei_open_third_lanes",
            row,
            args.city,
            lane_pattern="yes|yes|yes",
            restriction_type="motorcycle_lane_allowed",
        )
        inserted += 1
    return inserted


def fetch_reference_only(
    session: requests.Session,
    url: str,
    raw_dir: Path,
    dataset: str,
) -> int:
    return len(fetch_csv(session, url, raw_dir, dataset))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load Taipei motorcycle open-data CSV resources into the existing raw_tdx schema.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--dataset",
        choices=(
            "all",
            "two_stage_turns",
            "motorcycle_bans",
            "open_third_lanes",
            "direct_left_reference",
        ),
        default="all",
    )
    parser.add_argument("--city", default=os.getenv("TAIPEI_CITY", DEFAULT_CITY))
    parser.add_argument("--district", default=os.getenv("TAIPEI_DISTRICT", DEFAULT_DISTRICT))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--raw-dir", type=Path, default=Path(os.getenv("TAIPEI_RAW_DIR", "data/raw/taipei")))
    parser.add_argument("--two-stage-turn-url", default=os.getenv("TAIPEI_TWO_STAGE_TURN_URL", DEFAULT_TWO_STAGE_TURN_URL))
    parser.add_argument("--direct-left-url", default=os.getenv("TAIPEI_DIRECT_LEFT_URL", DEFAULT_DIRECT_LEFT_URL))
    parser.add_argument("--open-third-lane-url", default=os.getenv("TAIPEI_OPEN_THIRD_LANE_URL", DEFAULT_OPEN_THIRD_LANE_URL))
    parser.add_argument("--motorcycle-ban-url", default=os.getenv("TAIPEI_MOTORCYCLE_BAN_URL", DEFAULT_MOTORCYCLE_BAN_URL))
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser


def resolve_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    parser = build_parser()
    args = parser.parse_args()
    args.district = args.district.strip() or None
    return args


def main() -> int:
    args = resolve_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )

    started_at = datetime.now(timezone.utc)
    inserted: dict[str, int] = {}
    with requests.Session() as session, psycopg2.connect(args.database_url) as conn:
        if args.dataset in {"all", "two_stage_turns"}:
            inserted["two_stage_turns"] = ingest_two_stage_turns(conn, session, args)
        if args.dataset in {"all", "motorcycle_bans"}:
            inserted["motorcycle_bans"] = ingest_motorcycle_bans(conn, session, args)
        if args.dataset in {"all", "open_third_lanes"}:
            inserted["open_third_lanes"] = ingest_open_third_lanes(conn, session, args)
        if args.dataset in {"all", "direct_left_reference"}:
            inserted["direct_left_reference"] = fetch_reference_only(
                session,
                args.direct_left_url,
                args.raw_dir,
                "taipei_direct_left_reference",
            )

        record_ingest_run(
            conn,
            "taipei_open_data",
            "data.taipei",
            sum(inserted.values()),
            started_at,
            {
                "city": args.city,
                "district": args.district,
                "inserted": inserted,
                "raw_dir": str(args.raw_dir),
            },
        )
        conn.commit()

    for dataset, count in inserted.items():
        LOGGER.info("Loaded %s %s rows", count, dataset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
