from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import psycopg2
import requests
from psycopg2.extras import Json
from script_utils import load_env_file, parse_bbox


LOGGER = logging.getLogger("tdx_ingest")

DEFAULT_AUTH_URL = (
    "https://tdx.transportdata.tw/auth/realms/TDXConnect/"
    "protocol/openid-connect/token"
)
DEFAULT_API_BASE_URL = "https://tdx.transportdata.tw/api/basic/v2"
DEFAULT_BBOX = "121.5150,25.0150,121.5650,25.0500"

WKT_RE = re.compile(
    r"^\s*(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\s",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+)")
GEOJSON_TYPES = {
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
    "GeometryCollection",
}


def parse_json_object(raw: str | None, label: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def valid_taiwan_lonlat(lon: Any, lat: Any) -> bool:
    try:
        lon_f = float(lon)
        lat_f = float(lat)
    except (TypeError, ValueError):
        return False
    return 118.0 <= lon_f <= 123.5 and 21.0 <= lat_f <= 26.5


def endpoint_to_url(endpoint: str, base_url: str) -> str:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    return urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))


def get_access_token(
    session: requests.Session,
    auth_url: str,
    client_id: str,
    client_secret: str,
) -> str:
    response = session.post(
        auth_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("TDX auth response did not contain access_token")
    return token


def normalize_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("value"), list):
            items = payload["value"]
        elif isinstance(payload.get("data"), list):
            items = payload["data"]
        elif isinstance(payload.get("Data"), list):
            items = payload["Data"]
        else:
            items = [payload]
    else:
        items = []
    return [item for item in items if isinstance(item, dict)]


def fetch_pages(
    session: requests.Session,
    url: str,
    token: str,
    params: dict[str, Any],
    page_size: int,
    max_pages: int,
    raw_dir: Path,
    dataset_name: str,
) -> list[dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    items: list[dict[str, Any]] = []

    for page in range(max_pages):
        request_params = dict(params)
        request_params.setdefault("$format", "JSON")
        request_params.setdefault("$top", page_size)
        request_params["$skip"] = page * page_size

        LOGGER.info("Fetching %s page %s from %s", dataset_name, page + 1, url)
        response = session.get(url, headers=headers, params=request_params, timeout=60)
        response.raise_for_status()
        payload = response.json()

        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = raw_dir / f"{dataset_name}_page_{page + 1}.json"
        raw_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        page_items = normalize_payload(payload)
        items.extend(page_items)
        if len(page_items) < int(request_params["$top"]):
            break

    return items


def find_lonlat(obj: Any) -> tuple[float, float] | None:
    if isinstance(obj, dict):
        pairs = [
            ("PositionLon", "PositionLat"),
            ("Longitude", "Latitude"),
            ("longitude", "latitude"),
            ("Lon", "Lat"),
            ("lon", "lat"),
            ("Lng", "Lat"),
            ("lng", "lat"),
            ("X", "Y"),
            ("x", "y"),
        ]
        for lon_key, lat_key in pairs:
            if lon_key in obj and lat_key in obj and valid_taiwan_lonlat(obj[lon_key], obj[lat_key]):
                return float(obj[lon_key]), float(obj[lat_key])

        for value in obj.values():
            found = find_lonlat(value)
            if found:
                return found

    if isinstance(obj, list):
        for value in obj:
            found = find_lonlat(value)
            if found:
                return found

    return None


def find_wkt(obj: Any) -> str | None:
    if isinstance(obj, str) and WKT_RE.match(obj):
        return obj
    if isinstance(obj, dict):
        for key in ("WKT", "Wkt", "wkt", "Geometry", "geometry", "GeoWKT", "Geo"):
            value = obj.get(key)
            if isinstance(value, str) and WKT_RE.match(value):
                return value
        for value in obj.values():
            found = find_wkt(value)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = find_wkt(value)
            if found:
                return found
    return None


def find_geojson(obj: Any) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        geo_type = obj.get("type")
        if geo_type in GEOJSON_TYPES:
            return obj
        for key in ("GeoJSON", "geojson", "Geometry", "geometry", "Geo"):
            value = obj.get(key)
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict) and parsed.get("type") in GEOJSON_TYPES:
                    return parsed
            elif isinstance(value, dict) and value.get("type") in GEOJSON_TYPES:
                return value
        for value in obj.values():
            found = find_geojson(value)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = find_geojson(value)
            if found:
                return found
    return None


def geometry_from_record(record: dict[str, Any]) -> tuple[str, Any] | None:
    geojson = find_geojson(record)
    if geojson:
        return "geojson", geojson

    wkt = find_wkt(record)
    if wkt:
        return "wkt", wkt

    lonlat = find_lonlat(record)
    if lonlat:
        return "point", lonlat

    return None


def wkt_intersects_bbox(wkt: str, bbox: tuple[float, float, float, float]) -> bool:
    numbers = [float(value) for value in NUMBER_RE.findall(wkt)]
    for index in range(0, len(numbers) - 1, 2):
        lon, lat = numbers[index], numbers[index + 1]
        if valid_taiwan_lonlat(lon, lat) and in_bbox(lon, lat, bbox):
            return True
    return False


def geojson_intersects_bbox(geojson: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    def walk_coordinates(value: Any) -> bool:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            lon, lat = float(value[0]), float(value[1])
            return valid_taiwan_lonlat(lon, lat) and in_bbox(lon, lat, bbox)
        if isinstance(value, list):
            return any(walk_coordinates(item) for item in value)
        return False

    if geojson.get("type") == "GeometryCollection":
        return any(
            geojson_intersects_bbox(geom, bbox)
            for geom in geojson.get("geometries", [])
            if isinstance(geom, dict)
        )
    return walk_coordinates(geojson.get("coordinates"))


def record_matches_bbox(record: dict[str, Any], bbox: tuple[float, float, float, float] | None) -> bool:
    if not bbox:
        return True

    geometry = geometry_from_record(record)
    if not geometry:
        return True

    geom_type, geom_value = geometry
    if geom_type == "point":
        lon, lat = geom_value
        return in_bbox(lon, lat, bbox)
    if geom_type == "wkt":
        return wkt_intersects_bbox(geom_value, bbox)
    if geom_type == "geojson":
        return geojson_intersects_bbox(geom_value, bbox)
    return True


def pick_first(obj: Any, candidates: tuple[str, ...]) -> str | None:
    if isinstance(obj, dict):
        for key in candidates:
            value = obj.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                return str(value)
        for value in obj.values():
            found = pick_first(value, candidates)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = pick_first(value, candidates)
            if found:
                return found
    return None


def source_id(record: dict[str, Any]) -> str:
    direct = pick_first(
        record,
        (
            "UID",
            "Id",
            "ID",
            "id",
            "IntersectionID",
            "RoadID",
            "LinkID",
            "LaneID",
            "ObjectID",
        ),
    )
    if direct:
        return direct
    stable = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def geometry_sql(record: dict[str, Any]) -> tuple[str, list[Any]]:
    geometry = geometry_from_record(record)
    if not geometry:
        return "NULL", []

    geom_type, geom_value = geometry
    if geom_type == "point":
        lon, lat = geom_value
        return "ST_SetSRID(ST_MakePoint(%s, %s), 4326)", [lon, lat]
    if geom_type == "wkt":
        return "ST_SetSRID(ST_GeomFromText(%s), 4326)", [geom_value]
    if geom_type == "geojson":
        return "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)", [json.dumps(geom_value)]

    return "NULL", []


def insert_waiting_zone(
    conn: psycopg2.extensions.connection,
    endpoint: str,
    record: dict[str, Any],
    city: str,
    district: str,
) -> None:
    geom_expr, geom_params = geometry_sql(record)
    params = [
        endpoint,
        source_id(record),
        city,
        district,
        pick_first(record, ("Name", "name", "IntersectionName", "LocationName")),
        pick_first(record, ("RoadName", "road_name", "Road", "RoadSection")),
        pick_first(record, ("Direction", "direction", "TravelDirection")),
        Json(record),
    ]
    sql = f"""
        INSERT INTO raw_tdx.motorcycle_waiting_zones
            (source_endpoint, source_id, city, district, name, road_name, direction, raw, geom)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {geom_expr})
        ON CONFLICT (source_endpoint, source_id) DO UPDATE SET
            city = EXCLUDED.city,
            district = EXCLUDED.district,
            name = EXCLUDED.name,
            road_name = EXCLUDED.road_name,
            direction = EXCLUDED.direction,
            raw = EXCLUDED.raw,
            geom = EXCLUDED.geom,
            fetched_at = now()
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + geom_params)


def insert_lane_restriction(
    conn: psycopg2.extensions.connection,
    endpoint: str,
    record: dict[str, Any],
    city: str,
    district: str,
) -> None:
    geom_expr, geom_params = geometry_sql(record)
    params = [
        endpoint,
        source_id(record),
        city,
        district,
        pick_first(record, ("RoadName", "road_name", "Road", "RoadSection")),
        pick_first(record, ("Direction", "direction", "TravelDirection")),
        pick_first(record, ("LanePattern", "MotorcycleLanes", "LaneRestriction", "Lane", "Lanes")),
        pick_first(record, ("RestrictionType", "Restriction", "MotorcycleRestriction"))
        or "motorcycle_lane_restriction",
        Json(record),
    ]
    sql = f"""
        INSERT INTO raw_tdx.motorcycle_lane_restrictions
            (
                source_endpoint, source_id, city, district, road_name, direction,
                lane_pattern, restriction_type, raw, geom
            )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, {geom_expr})
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
    """
    with conn.cursor() as cur:
        cur.execute(sql, params + geom_params)


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


def ingest_dataset(
    conn: psycopg2.extensions.connection,
    session: requests.Session,
    token: str,
    dataset: str,
    endpoint: str,
    params: dict[str, Any],
    args: argparse.Namespace,
) -> int:
    started_at = datetime.now(timezone.utc)
    url = endpoint_to_url(endpoint, args.tdx_api_base_url)
    rows = fetch_pages(
        session=session,
        url=url,
        token=token,
        params=params,
        page_size=args.page_size,
        max_pages=args.max_pages,
        raw_dir=args.raw_dir,
        dataset_name=dataset,
    )

    inserted = 0
    for row in rows:
        if not record_matches_bbox(row, args.bbox):
            continue
        if dataset == "waiting_zones":
            insert_waiting_zone(conn, endpoint, row, args.city, args.district)
        elif dataset == "lane_restrictions":
            insert_lane_restriction(conn, endpoint, row, args.city, args.district)
        else:
            raise ValueError(f"Unsupported dataset: {dataset}")
        inserted += 1

    record_ingest_run(
        conn,
        dataset,
        endpoint,
        inserted,
        started_at,
        {
            "bbox": args.bbox,
            "params": params,
            "raw_rows": len(rows),
            "url": url,
        },
    )
    conn.commit()
    LOGGER.info("Inserted or updated %s %s rows", inserted, dataset)
    return inserted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch TDX motorcycle-related datasets and load them into PostGIS.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--dataset", choices=("all", "waiting_zones", "lane_restrictions"), default="all")
    parser.add_argument("--city", default=os.getenv("INGEST_CITY", "Taipei"))
    parser.add_argument("--district", default=os.getenv("INGEST_DISTRICT", "Da'an"))
    parser.add_argument("--bbox", default=os.getenv("INGEST_BBOX", DEFAULT_BBOX))
    parser.add_argument("--page-size", type=int, default=int(os.getenv("TDX_PAGE_SIZE", "1000")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("TDX_MAX_PAGES", "10")))
    parser.add_argument("--raw-dir", type=Path, default=Path(os.getenv("TDX_RAW_DIR", "data/raw/tdx")))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--tdx-auth-url", default=os.getenv("TDX_AUTH_URL", DEFAULT_AUTH_URL))
    parser.add_argument("--tdx-api-base-url", default=os.getenv("TDX_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--waiting-zones-endpoint", default=os.getenv("TDX_WAITING_ZONES_ENDPOINT"))
    parser.add_argument("--lane-restrictions-endpoint", default=os.getenv("TDX_LANE_RESTRICTIONS_ENDPOINT"))
    parser.add_argument("--waiting-zones-params", default=os.getenv("TDX_WAITING_ZONES_PARAMS"))
    parser.add_argument("--lane-restrictions-params", default=os.getenv("TDX_LANE_RESTRICTIONS_PARAMS"))
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser


def resolve_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    parser = build_parser()
    args = parser.parse_args()
    args.bbox = parse_bbox(args.bbox)
    return args


def main() -> int:
    args = resolve_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )

    client_id = os.getenv("TDX_CLIENT_ID")
    client_secret = os.getenv("TDX_CLIENT_SECRET")
    if not client_id or not client_secret:
        LOGGER.error("Set TDX_CLIENT_ID and TDX_CLIENT_SECRET in .env or environment.")
        return 2
    if not args.database_url:
        LOGGER.error("Set DATABASE_URL in .env or pass --database-url.")
        return 2

    selected: list[tuple[str, str | None, dict[str, Any]]] = []
    if args.dataset in ("all", "waiting_zones"):
        selected.append(
            (
                "waiting_zones",
                args.waiting_zones_endpoint,
                parse_json_object(args.waiting_zones_params, "TDX_WAITING_ZONES_PARAMS"),
            )
        )
    if args.dataset in ("all", "lane_restrictions"):
        selected.append(
            (
                "lane_restrictions",
                args.lane_restrictions_endpoint,
                parse_json_object(args.lane_restrictions_params, "TDX_LANE_RESTRICTIONS_PARAMS"),
            )
        )

    missing = [name for name, endpoint, _ in selected if not endpoint]
    if missing:
        LOGGER.error("Missing endpoint config for: %s", ", ".join(missing))
        LOGGER.error("Fill TDX_WAITING_ZONES_ENDPOINT and/or TDX_LANE_RESTRICTIONS_ENDPOINT in .env.")
        return 2

    with requests.Session() as session:
        token = get_access_token(session, args.tdx_auth_url, client_id, client_secret)
        with psycopg2.connect(args.database_url) as conn:
            total = 0
            for dataset, endpoint, params in selected:
                total += ingest_dataset(conn, session, token, dataset, endpoint or "", params, args)

    LOGGER.info("TDX ingest completed. Total rows: %s", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
