from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import osmium
import psycopg2
from psycopg2.extras import Json, execute_values
from script_utils import load_env_file, parse_bbox


LOGGER = logging.getLogger("osm_tdx_fusion")

DEFAULT_DATABASE_URL = "postgresql://tw_nav:tw_nav_dev_password@localhost:5432/tw_nav"
DEFAULT_BBOX = "121.5150,25.0150,121.5650,25.0500"
DEFAULT_OUTPUT_PBF = "infra/valhalla/custom_files/taiwan_custom.pbf"

MOTORABLE_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "road",
}

NON_MOTORCYCLE_ACCESS = {"no", "private", "delivery", "customers", "emergency"}
LANE_TOKEN_RE = re.compile(r"\b(no|yes|designated|permissive|destination|private)\b")
SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sql_normalized_road_name(expression: str) -> str:
    return f"""
        regexp_replace(
            regexp_replace(
                replace(lower(COALESCE({expression}, '')), '臺', '台'),
                '[[:space:]]+',
                '',
                'g'
            ),
            '[0-9一二三四五六七八九十\\-]+段',
            '',
            'g'
        )
    """


def expand_bbox(
    bbox: tuple[float, float, float, float] | None,
    margin_degrees: float,
) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        min_lon - margin_degrees,
        min_lat - margin_degrees,
        max_lon + margin_degrees,
        max_lat + margin_degrees,
    )


def in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float] | None) -> bool:
    if not bbox:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def is_motorcycle_candidate(tags: dict[str, str]) -> bool:
    highway = tags.get("highway")
    if highway not in MOTORABLE_HIGHWAYS:
        return False
    if tags.get("area") == "yes":
        return False
    if tags.get("motor_vehicle") in NON_MOTORCYCLE_ACCESS:
        return False
    if tags.get("access") in {"private", "emergency"}:
        return False
    return True


def has_node_in_bbox(nodes: osmium.osm.NodeRefList, bbox: tuple[float, float, float, float] | None) -> bool:
    if not bbox:
        return True
    for node in nodes:
        if node.location.valid() and in_bbox(node.lon, node.lat, bbox):
            return True
    return False


def setup_fusion_schema(conn: psycopg2.extensions.connection, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cur.execute(f"DROP TABLE IF EXISTS {schema}.osm_highway_nodes")
        cur.execute(f"DROP TABLE IF EXISTS {schema}.osm_highway_ways")
        cur.execute(f"DROP TABLE IF EXISTS {schema}.node_two_stage_turns")
        cur.execute(f"DROP TABLE IF EXISTS {schema}.way_motorcycle_lanes")

        cur.execute(
            f"""
            CREATE UNLOGGED TABLE {schema}.osm_highway_nodes (
                osm_id BIGINT PRIMARY KEY,
                geom geometry(Point, 4326) NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE {schema}.osm_highway_ways (
                osm_id BIGINT PRIMARY KEY,
                highway TEXT,
                name TEXT,
                tags JSONB NOT NULL,
                node_ids BIGINT[] NOT NULL,
                geom geometry(LineString, 4326) NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE {schema}.node_two_stage_turns (
                osm_node_id BIGINT PRIMARY KEY,
                source_id TEXT,
                distance_m DOUBLE PRECISION
            )
            """
        )
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE {schema}.way_motorcycle_lanes (
                osm_way_id BIGINT PRIMARY KEY,
                lane_pattern TEXT,
                restriction_type TEXT,
                source_id TEXT,
                distance_m DOUBLE PRECISION
            )
            """
        )
    conn.commit()


def index_fusion_schema(conn: psycopg2.extensions.connection, schema: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{schema}_osm_highway_nodes_geom ON {schema}.osm_highway_nodes USING GIST (geom)")
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{schema}_osm_highway_ways_geom ON {schema}.osm_highway_ways USING GIST (geom)")
        cur.execute(f"ANALYZE {schema}.osm_highway_nodes")
        cur.execute(f"ANALYZE {schema}.osm_highway_ways")
    conn.commit()


class HighwayStageHandler(osmium.SimpleHandler):
    def __init__(
        self,
        conn: psycopg2.extensions.connection,
        schema: str,
        bbox: tuple[float, float, float, float] | None,
        batch_size: int,
    ) -> None:
        super().__init__()
        self.conn = conn
        self.schema = schema
        self.bbox = bbox
        self.batch_size = batch_size
        self.wkt_factory = osmium.geom.WKTFactory()
        self.node_rows: list[tuple[int, float, float]] = []
        self.way_rows: list[tuple[int, str | None, str | None, Json, list[int], str]] = []
        self.seen_nodes: set[int] = set()
        self.ways_seen = 0
        self.ways_staged = 0
        self.nodes_staged = 0

    def way(self, way: osmium.osm.Way) -> None:
        tags = dict(way.tags)
        if not is_motorcycle_candidate(tags):
            return
        if not has_node_in_bbox(way.nodes, self.bbox):
            return

        try:
            wkt = self.wkt_factory.create_linestring(way.nodes)
        except Exception as exc:
            LOGGER.debug("Skipping way %s due to invalid geometry: %s", way.id, exc)
            return

        node_ids: list[int] = []
        for node in way.nodes:
            node_ids.append(node.ref)
            if (
                node.location.valid()
                and in_bbox(node.lon, node.lat, self.bbox)
                and node.ref not in self.seen_nodes
            ):
                self.seen_nodes.add(node.ref)
                self.node_rows.append((node.ref, float(node.lon), float(node.lat)))

        self.way_rows.append(
            (
                way.id,
                tags.get("highway"),
                tags.get("name"),
                Json(tags),
                node_ids,
                wkt,
            )
        )
        self.ways_seen += 1

        if len(self.node_rows) >= self.batch_size or len(self.way_rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        with self.conn.cursor() as cur:
            if self.node_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {self.schema}.osm_highway_nodes (osm_id, geom)
                    VALUES %s
                    ON CONFLICT (osm_id) DO NOTHING
                    """,
                    self.node_rows,
                    template="(%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))",
                    page_size=self.batch_size,
                )
                self.nodes_staged += len(self.node_rows)
                self.node_rows.clear()

            if self.way_rows:
                execute_values(
                    cur,
                    f"""
                    INSERT INTO {self.schema}.osm_highway_ways
                        (osm_id, highway, name, tags, node_ids, geom)
                    VALUES %s
                    ON CONFLICT (osm_id) DO UPDATE SET
                        highway = EXCLUDED.highway,
                        name = EXCLUDED.name,
                        tags = EXCLUDED.tags,
                        node_ids = EXCLUDED.node_ids,
                        geom = EXCLUDED.geom
                    """,
                    self.way_rows,
                    template="(%s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))",
                    page_size=self.batch_size,
                )
                self.ways_staged += len(self.way_rows)
                self.way_rows.clear()
        self.conn.commit()


def build_spatial_annotations(
    conn: psycopg2.extensions.connection,
    schema: str,
    waiting_zone_buffer_m: float,
    lane_restriction_buffer_m: float,
    default_lane_pattern: str,
) -> None:
    waiting_zone_deg = waiting_zone_buffer_m / 111_320.0
    lane_restriction_deg = lane_restriction_buffer_m / 111_320.0

    with conn.cursor() as cur:
        LOGGER.info("Matching TDX motorcycle waiting zones to OSM road nodes")
        cur.execute(
            f"""
            INSERT INTO {schema}.node_two_stage_turns (osm_node_id, source_id, distance_m)
            SELECT osm_node_id, source_id, distance_m
            FROM (
                SELECT DISTINCT ON (n.osm_id)
                    n.osm_id AS osm_node_id,
                    z.source_id,
                    ST_Distance(n.geom::geography, z.geom::geography) AS distance_m
                FROM {schema}.osm_highway_nodes n
                JOIN raw_tdx.motorcycle_waiting_zones z
                  ON z.geom IS NOT NULL
                 AND ST_DWithin(n.geom, z.geom, %s)
                 AND ST_DWithin(n.geom::geography, z.geom::geography, %s)
                ORDER BY n.osm_id, ST_Distance(n.geom::geography, z.geom::geography)
            ) matched
            ON CONFLICT (osm_node_id) DO UPDATE SET
                source_id = EXCLUDED.source_id,
                distance_m = EXCLUDED.distance_m
            """,
            (waiting_zone_deg, waiting_zone_buffer_m),
        )

        LOGGER.info("Matching text-only Taipei two-stage-turn rows to OSM road intersections")
        cur.execute(
            f"""
            WITH zone_roads AS (
                SELECT
                    z.source_id,
                    {sql_normalized_road_name("road.value")} AS road_name
                FROM raw_tdx.motorcycle_waiting_zones z
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(z.raw->'roads') = 'array'
                        THEN z.raw->'roads'
                        ELSE '[]'::jsonb
                    END
                ) AS road(value)
                WHERE z.geom IS NULL
            ),
            candidate_nodes AS (
                SELECT
                    n.osm_id AS osm_node_id,
                    zr.source_id,
                    COUNT(DISTINCT zr.road_name) AS matched_roads
                FROM {schema}.osm_highway_nodes n
                JOIN {schema}.osm_highway_ways w
                  ON n.osm_id = ANY(w.node_ids)
                JOIN zone_roads zr
                  ON {sql_normalized_road_name("w.name")} = zr.road_name
                WHERE zr.road_name <> ''
                GROUP BY n.osm_id, zr.source_id
                HAVING COUNT(DISTINCT zr.road_name) >= 2
            )
            INSERT INTO {schema}.node_two_stage_turns
                (osm_node_id, source_id, distance_m)
            SELECT DISTINCT ON (osm_node_id)
                osm_node_id,
                source_id,
                NULL::DOUBLE PRECISION AS distance_m
            FROM candidate_nodes
            ORDER BY osm_node_id, matched_roads DESC, source_id
            ON CONFLICT (osm_node_id) DO NOTHING
            """
        )

        LOGGER.info("Matching TDX motorcycle lane restrictions to OSM ways")
        cur.execute(
            f"""
            INSERT INTO {schema}.way_motorcycle_lanes
                (osm_way_id, lane_pattern, restriction_type, source_id, distance_m)
            SELECT osm_way_id, lane_pattern, restriction_type, source_id, distance_m
            FROM (
                SELECT DISTINCT ON (w.osm_id)
                    w.osm_id AS osm_way_id,
                    COALESCE(NULLIF(r.lane_pattern, ''), %s) AS lane_pattern,
                    r.restriction_type,
                    r.source_id,
                    ST_Distance(w.geom::geography, r.geom::geography) AS distance_m
                FROM {schema}.osm_highway_ways w
                JOIN raw_tdx.motorcycle_lane_restrictions r
                  ON r.geom IS NOT NULL
                 AND ST_DWithin(w.geom, r.geom, %s)
                 AND ST_DWithin(w.geom::geography, r.geom::geography, %s)
                ORDER BY w.osm_id, ST_Distance(w.geom::geography, r.geom::geography)
            ) matched
            ON CONFLICT (osm_way_id) DO UPDATE SET
                lane_pattern = EXCLUDED.lane_pattern,
                restriction_type = EXCLUDED.restriction_type,
                source_id = EXCLUDED.source_id,
                distance_m = EXCLUDED.distance_m
            """,
            (default_lane_pattern, lane_restriction_deg, lane_restriction_buffer_m),
        )

        LOGGER.info("Matching text-only Taipei motorcycle lane restrictions to OSM ways")
        cur.execute(
            f"""
            WITH restriction_roads AS (
                SELECT
                    r.source_id,
                    COALESCE(NULLIF(r.lane_pattern, ''), %s) AS lane_pattern,
                    r.restriction_type,
                    {sql_normalized_road_name("road.value")} AS road_name
                FROM raw_tdx.motorcycle_lane_restrictions
                r
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(r.raw->'roads') = 'array'
                        THEN r.raw->'roads'
                        WHEN COALESCE(r.road_name, '') <> ''
                        THEN jsonb_build_array(r.road_name)
                        ELSE '[]'::jsonb
                    END
                ) AS road(value)
                WHERE r.geom IS NULL
            ),
            matched AS (
                SELECT DISTINCT ON (w.osm_id)
                    w.osm_id AS osm_way_id,
                    r.lane_pattern,
                    r.restriction_type,
                    r.source_id,
                    NULL::DOUBLE PRECISION AS distance_m
                FROM {schema}.osm_highway_ways w
                JOIN restriction_roads r
                  ON {sql_normalized_road_name("w.name")} = r.road_name
                WHERE r.road_name <> ''
                ORDER BY
                    w.osm_id,
                    CASE
                        WHEN lower(COALESCE(r.restriction_type, '')) = 'motorcycle=no'
                        THEN 0
                        ELSE 1
                    END,
                    r.source_id
            )
            INSERT INTO {schema}.way_motorcycle_lanes
                (osm_way_id, lane_pattern, restriction_type, source_id, distance_m)
            SELECT osm_way_id, lane_pattern, restriction_type, source_id, distance_m
            FROM matched
            ON CONFLICT (osm_way_id) DO NOTHING
            """,
            (default_lane_pattern,),
        )
    conn.commit()


def load_node_annotations(conn: psycopg2.extensions.connection, schema: str) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT osm_node_id FROM {schema}.node_two_stage_turns")
        return {row[0] for row in cur.fetchall()}


def load_way_annotations(conn: psycopg2.extensions.connection, schema: str) -> dict[int, tuple[str, str | None]]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT osm_way_id, lane_pattern, restriction_type FROM {schema}.way_motorcycle_lanes")
        return {row[0]: (row[1], row[2]) for row in cur.fetchall()}


def normalize_lane_pattern(raw: str | None, default_lane_pattern: str) -> str:
    if not raw:
        return default_lane_pattern

    normalized = raw.strip().lower()
    if "|" in normalized:
        tokens = [token.strip() for token in normalized.split("|")]
        if tokens and all(token in {"no", "yes", "designated", "permissive", "private"} for token in tokens):
            return "|".join(tokens)

    tokens = LANE_TOKEN_RE.findall(normalized)
    if len(tokens) >= 2:
        return "|".join(tokens)

    if any(keyword in raw for keyword in ("內側", "內車道", "禁行機車")):
        return default_lane_pattern
    if "inner" in normalized or "left" in normalized:
        return default_lane_pattern

    return default_lane_pattern


def should_block_motorcycle_access(lane_pattern: str, restriction_type: str | None) -> bool:
    normalized_type = (restriction_type or "").strip().lower()
    if normalized_type in {"motorcycle=no", "motorcycle_no", "no_motorcycle", "closed_to_motorcycles"}:
        return True

    lanes = [lane.strip().lower() for lane in lane_pattern.split("|") if lane.strip()]
    return bool(lanes) and all(lane == "no" for lane in lanes)


class PbfRewriteHandler(osmium.SimpleHandler):
    def __init__(
        self,
        writer: osmium.SimpleWriter,
        two_stage_nodes: set[int],
        way_lane_patterns: dict[int, tuple[str, str | None]],
        default_lane_pattern: str,
    ) -> None:
        super().__init__()
        self.writer = writer
        self.two_stage_nodes = two_stage_nodes
        self.way_lane_patterns = way_lane_patterns
        self.default_lane_pattern = default_lane_pattern
        self.nodes_tagged = 0
        self.ways_tagged = 0

    def node(self, node: osmium.osm.Node) -> None:
        if node.id in self.two_stage_nodes:
            tags = dict(node.tags)
            tags["restriction:motorcycle"] = "two_stage_turn"
            tags["tdx:motorcycle_waiting_zone"] = "yes"
            self.writer.add(node.replace(tags=tags))
            self.nodes_tagged += 1
            return

        self.writer.add(node)

    def way(self, way: osmium.osm.Way) -> None:
        annotation = self.way_lane_patterns.get(way.id)
        if annotation:
            lane_pattern, restriction_type = annotation
            normalized_lane_pattern = normalize_lane_pattern(lane_pattern, self.default_lane_pattern)
            tags = dict(way.tags)
            tags["motorcycle:lanes"] = normalized_lane_pattern
            if should_block_motorcycle_access(normalized_lane_pattern, restriction_type):
                tags["motorcycle"] = "no"
            tags["tdx:motorcycle_lane_restriction"] = "yes"
            self.writer.add(way.replace(tags=tags))
            self.ways_tagged += 1
            return

        self.writer.add(way)

    def relation(self, relation: osmium.osm.Relation) -> None:
        self.writer.add(relation)


def write_fused_pbf(
    input_pbf: Path,
    output_pbf: Path,
    two_stage_nodes: set[int],
    way_lane_patterns: dict[int, tuple[str, str | None]],
    default_lane_pattern: str,
) -> tuple[int, int]:
    output_pbf.parent.mkdir(parents=True, exist_ok=True)
    with osmium.SimpleWriter(str(output_pbf), overwrite=True) as writer:
        handler = PbfRewriteHandler(
            writer=writer,
            two_stage_nodes=two_stage_nodes,
            way_lane_patterns=way_lane_patterns,
            default_lane_pattern=default_lane_pattern,
        )
        handler.apply_file(str(input_pbf))
        return handler.nodes_tagged, handler.ways_tagged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fuse raw TDX motorcycle restrictions into an OSM PBF for Valhalla.",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--input-pbf", type=Path, required=True)
    parser.add_argument("--output-pbf", type=Path, default=Path(os.getenv("FUSION_OUTPUT_PBF", DEFAULT_OUTPUT_PBF)))
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    parser.add_argument("--bbox", default=os.getenv("INGEST_BBOX", DEFAULT_BBOX))
    parser.add_argument("--bbox-margin-degrees", type=float, default=float(os.getenv("FUSION_BBOX_MARGIN_DEGREES", "0.02")))
    parser.add_argument("--schema", default=os.getenv("FUSION_SCHEMA", "fusion"))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("FUSION_BATCH_SIZE", "5000")))
    parser.add_argument("--location-index", default=os.getenv("OSMIUM_LOCATION_INDEX", "flex_mem"))
    parser.add_argument("--waiting-zone-buffer-m", type=float, default=float(os.getenv("WAITING_ZONE_BUFFER_M", "35")))
    parser.add_argument("--lane-restriction-buffer-m", type=float, default=float(os.getenv("LANE_RESTRICTION_BUFFER_M", "25")))
    parser.add_argument("--default-lane-pattern", default=os.getenv("DEFAULT_MOTORCYCLE_LANE_PATTERN", "no|yes|yes"))
    parser.add_argument("--skip-stage", action="store_true", help="Reuse existing fusion staging tables.")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser


def resolve_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    parser = build_parser()
    args = parser.parse_args()
    if not SQL_IDENTIFIER_RE.match(args.schema):
        raise ValueError("--schema must be a simple SQL identifier")
    args.bbox = expand_bbox(parse_bbox(args.bbox), args.bbox_margin_degrees)
    return args


def main() -> int:
    args = resolve_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )

    if not args.input_pbf.exists():
        LOGGER.error("Input PBF does not exist: %s", args.input_pbf)
        return 2

    with psycopg2.connect(args.database_url) as conn:
        if not args.skip_stage:
            LOGGER.info("Preparing fusion staging schema: %s", args.schema)
            setup_fusion_schema(conn, args.schema)

            LOGGER.info("Staging OSM motorcycle candidate roads from %s", args.input_pbf)
            stage_handler = HighwayStageHandler(
                conn=conn,
                schema=args.schema,
                bbox=args.bbox,
                batch_size=args.batch_size,
            )
            stage_handler.apply_file(
                str(args.input_pbf),
                locations=True,
                idx=args.location_index,
            )
            stage_handler.flush()
            LOGGER.info(
                "Staged %s ways and %s road nodes",
                stage_handler.ways_staged,
                stage_handler.nodes_staged,
            )
            index_fusion_schema(conn, args.schema)

        build_spatial_annotations(
            conn=conn,
            schema=args.schema,
            waiting_zone_buffer_m=args.waiting_zone_buffer_m,
            lane_restriction_buffer_m=args.lane_restriction_buffer_m,
            default_lane_pattern=args.default_lane_pattern,
        )
        two_stage_nodes = load_node_annotations(conn, args.schema)
        way_lane_patterns = load_way_annotations(conn, args.schema)

    LOGGER.info(
        "Loaded %s two-stage-turn node tags and %s motorcycle lane tags",
        len(two_stage_nodes),
        len(way_lane_patterns),
    )
    tagged_nodes, tagged_ways = write_fused_pbf(
        input_pbf=args.input_pbf,
        output_pbf=args.output_pbf,
        two_stage_nodes=two_stage_nodes,
        way_lane_patterns=way_lane_patterns,
        default_lane_pattern=args.default_lane_pattern,
    )
    LOGGER.info(
        "Wrote %s with %s tagged nodes and %s tagged ways",
        args.output_pbf,
        tagged_nodes,
        tagged_ways,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
