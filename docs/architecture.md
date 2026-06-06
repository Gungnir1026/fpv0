# 系統架構

本專案是一個台灣機車導航 MVP。核心目標是把 OSM 道路、臺北市機車限制資料與 Valhalla 路由服務串起來，讓 Flutter App 可以顯示一般地圖、路線預覽與導航中的機車指引。

## 高層資料流

```text
OpenStreetMap PBF
        +
臺北市開放資料 CSV
        ↓
Python ETL
        ↓
PostgreSQL + PostGIS
        ↓
融合後 taiwan_custom.pbf
        ↓
Valhalla 圖磚 .gph / .tar
        ↓
Valhalla /route 與 /trace_route
        ↓
Flutter + MapLibre App
```

## 資料來源與格式

| 資料 | 格式 | 位置 | 用途 |
| --- | --- | --- | --- |
| OSM 原始道路 | OpenStreetMap Protocolbuffer Binary Format，副檔名 `.osm.pbf` | `data/raw/osm/taiwan-latest.osm.pbf` | 道路幾何、路口節點、道路分類、通行權限與 OSM 標籤。 |
| 臺北市開放資料 | CSV 文字檔，來源常見編碼為 Big5/CP950 | `data/raw/taipei/*.csv` | 機車待轉、禁行機車、開放第三車道與可直接左轉參考資料。 |
| TDX 可選資料 | JSON API response | `data/raw/tdx/` | 保留作為未來資料來源；目前 MVP 不需要 TDX 憑證即可執行。 |
| PostGIS 原始資料 | PostgreSQL table + `JSONB` + `geometry(Geometry, 4326)` | Docker volume `postgis_data` | 保存原始列資料、空間幾何與匯入紀錄。 |
| 融合後圖資 | `.pbf` | `infra/valhalla/custom_files/taiwan_custom.pbf` | 帶有台灣機車限制標籤的 Valhalla 建置輸入。 |
| Valhalla 圖磚 | `.gph`、`.tar`、SQLite 支援檔 | `infra/valhalla/custom_files/` | Valhalla 實際用來搜尋路線的本機建置產物。 |

## PostGIS 資料模型

資料庫初始化位於 `infra/postgres/init/001_enable_postgis.sql`。目前主要 schema 為 `raw_tdx`，雖然名稱保留 TDX，但現階段預設寫入臺北市開放資料。

| 表格 | 內容 |
| --- | --- |
| `raw_tdx.motorcycle_waiting_zones` | 機車待轉區與待轉路口資料。 |
| `raw_tdx.motorcycle_lane_restrictions` | 禁行機車、開放第三車道等道路或車道限制。 |
| `raw_tdx.ingest_runs` | 每次匯入的資料集、來源、筆數、時間與 metadata。 |

每筆來源資料會保留在 `raw JSONB`，方便未來回查原始欄位。若來源資料有座標，會寫入 `geom` 並透過 GiST index 加速空間媒合；臺北市 CSV 多數是路名與路口文字，因此目前主要依賴文字正規化與路口道路組合媒合。

## ETL 與融合流程

1. `scripts/taipei_open_data_ingest.py` 下載臺北市 CSV，處理 Big5/CP950/UTF-8 解碼，並寫入 PostGIS。
2. `scripts/osm_tdx_fusion.py` 使用 `osmium` 讀取 OSM PBF，將目標區域內可供機動車行駛的道路暫存到 PostGIS。
3. 融合腳本用兩種方式比對限制資料：
   - 有幾何資料時，以 `ST_DWithin` 與 `ST_Distance` 做空間媒合。
   - 沒有幾何資料時，以正規化路名、路段與路口道路組合做文字媒合。
4. 融合後重新輸出 `taiwan_custom.pbf`，供 Valhalla 建置圖磚。

## 融合後的台灣機車標籤

| 標籤 | 寫入位置 | 目前用途 |
| --- | --- | --- |
| `restriction:motorcycle=two_stage_turn` | OSM node | 表示路口有機車兩段式左轉語意；目前供後續 Valhalla 客製化與前端解析預備。 |
| `tdx:motorcycle_waiting_zone=yes` | OSM node | 標記資料來源命中，方便除錯與後續查詢。 |
| `motorcycle:lanes=no|yes|yes` | OSM way | 表示車道級機車通行狀態；目前主要供前端車道 UI 預備。 |
| `tdx:motorcycle_lane_restriction=yes` | OSM way | 標記道路曾命中機車車道限制資料。 |
| `motorcycle=no` | OSM way | 標準 OSM 通行限制；原生 Valhalla `motorcycle` costing 可排除此道路。 |

## 後端服務

`docker-compose.yml` 啟動兩個服務：

| 服務 | 容器 | Port | 責任 |
| --- | --- | --- | --- |
| PostGIS | `tw-nav-postgis` | `5432` | 儲存 ETL 原始資料與融合暫存資料。 |
| Valhalla | `tw-nav-valhalla` | `8002` | 建置並提供路由圖磚、`/route`、`/trace_route` 與 `/status`。 |

Valhalla 會從 `infra/valhalla/custom_files` 掛載 `valhalla.json`、融合後 PBF 與已建置圖磚。路由服務本身不直接讀取 PostGIS；PostGIS 只在資料匯入與 PBF 融合階段使用。

`scripts/taiwan_motorcycle_route_facade.py` 是目前的輕量後端語意橋接工具。它會呼叫 Valhalla `/route`，再用融合後 PBF 的待轉節點與車道標籤補上 maneuver 層級的 `taiwan_motorcycle`、`custom`、`motorcycle:lanes` 與 `restriction:motorcycle` 欄位。這讓 Flutter UI 可以先接上真實資料語意；但它不會改變 stock Valhalla 的選路成本。

## 路由與導航演算法

App 呼叫 Valhalla `/route` 時，送出起點、終點與 `costing: motorcycle`。Valhalla 的流程可分為：

1. Loki 將輸入座標定位到路由圖上的候選道路。
2. Sif 使用 motorcycle costing 計算道路、轉向與通行權限成本。
3. Thor 搜尋最低成本路徑；一般點對點路線使用 Valhalla 圖路由演算法。
4. Odin 產生 maneuver 與文字指引。
5. Flutter 解碼 `trip.legs[].shape`，在 MapLibre 上繪製路線。

導航中 App 也會定期呼叫 Meili `/trace_route`：

```json
{
  "shape": [
    {"lat": 25.0337, "lon": 121.5434},
    {"lat": 25.0329, "lon": 121.5410}
  ],
  "costing": "motorcycle",
  "shape_match": "map_snap"
}
```

Meili 的結果用於道路吸附與偏航判斷。App 只接受時間夠新且接近目前 raw GPS 的吸附點，避免舊吸附結果延遲重新規劃。

## 驗收工具

目前新增兩個後端與圖資驗收入口：

| 指令 | 用途 |
| --- | --- |
| `make audit-pbf-tags` | 使用 `scripts/pbf_tag_audit.py` 抽查 `taiwan_custom.pbf` 是否含有 `restriction:motorcycle=two_stage_turn`、`tdx:motorcycle_waiting_zone=yes`、`motorcycle:lanes`、`tdx:motorcycle_lane_restriction=yes` 與 `motorcycle=no`。預設為快速最低門檻抽查；需要精準全檔統計時可直接執行腳本並加上 `--full-scan`。 |
| `make test-golden-routes` | 使用 `scripts/valhalla_golden_routes.py` 讀取 `tests/golden_routes/daan_motorcycle_routes.json`，固定驗證三條大安區機車 baseline 路線的距離、時間、maneuver 數量、travel type 與必要道路名稱。 |
| `make test-valhalla-integration` | 使用 `scripts/valhalla_integration_test.py` 讀取 `tests/integration/valhalla_motorcycle_semantics.json`，驗證 auto control 會走 `民族陸橋`，而 motorcycle costing 會避開同一條 `motorcycle=no` 道路。 |
| `make route-facade-demo` | 呼叫 Valhalla 並用 `taiwan_custom.pbf` 補上 App 可解析的台灣機車語意欄位。 |

## Flutter App 狀態

App 目前有三種 session：

| 狀態 | 觸發方式 | 顯示內容 |
| --- | --- | --- |
| 一般地圖 | App 啟動或清除導航 | 底圖與定位點。 |
| 路線預覽 | 長按地圖選擇目的地 | 目的地、規劃路線、距離、ETA 與開始導航按鈕。 |
| 導航中 | 按下開始導航 | 路線、定位、下一步 maneuver、車道 UI、虛擬待轉區與偏航重規劃。 |

導航中若目前位置距離路線超過門檻，且距離上次規劃已超過最短間隔，App 會重新呼叫 `/route`。

## 目前已生效與尚未生效

已生效：

- OSM 與臺北市資料可融合並輸出 `taiwan_custom.pbf`。
- 原生 Valhalla 可依照標準 `motorcycle=no` 排除整條禁行道路，並已用 `make test-valhalla-integration` 驗證。
- `scripts/taiwan_motorcycle_route_facade.py` 可推導 maneuver 層級的 `taiwan_motorcycle`、`restriction:motorcycle=two_stage_turn` 與 `motorcycle:lanes` 欄位。
- Flutter 可顯示地圖、定位、路線預覽、導航狀態、偏航重規劃與 UI 層的車道/待轉區解析。
- Flutter parser 已可解析 `taiwan_motorcycle` 欄位，將後端推導的車道與待轉語意接回車道 UI 與虛擬待轉區。

尚未生效：

- `restriction:motorcycle=two_stage_turn` 尚未真正進入 Valhalla 圖磚成本模型。
- 兩段式左轉 `+90 秒` 懲罰需要客製 Valhalla Mjolnir 與 Sif，詳見 [valhalla-customization.md](valhalla-customization.md)。
- `motorcycle:lanes=no|yes|yes` 目前已可供 App UI 使用，但不等同於原生 Valhalla 的車道級避讓。
