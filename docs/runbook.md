# 台灣機車導航 MVP 操作手冊

本文件說明資料管線與各階段操作方式。日常啟停請優先參考 [getting-started.md](getting-started.md)。

## 階段一：啟動 PostGIS 與匯入交通資料

1. 建立本機環境設定：

   ```bash
   cp .env.example .env
   ```

2. 確認 `.env` 內臺北市開放資料設定：

   ```bash
   TAIPEI_CITY=臺北市
   TAIPEI_DISTRICT=大安區
   TAIPEI_TWO_STAGE_TURN_URL=...
   TAIPEI_MOTORCYCLE_BAN_URL=...
   TAIPEI_OPEN_THIRD_LANE_URL=...
   ```

   MVP 預設使用臺北市開放資料。除非日後切回 TDX，否則 `TDX_*` 可以留白。

3. 啟動 PostGIS：

   ```bash
   docker compose up -d postgis
   ```

4. 使用 `uv` 安裝 Python 依賴：

   ```bash
   UV_CACHE_DIR=.uv-cache uv sync
   ```

5. 將臺北市資料匯入 PostGIS：

   ```bash
   UV_CACHE_DIR=.uv-cache uv run python scripts/taipei_open_data_ingest.py --dataset all
   ```

此時 Valhalla 還沒有台灣路由圖磚。必須完成階段二並產生 `taiwan_custom.pbf`。

## 階段二：融合 OSM 與機車限制

1. 將台灣 OSM PBF 放在：

   ```text
   data/raw/osm/taiwan-latest.osm.pbf
   ```

2. 確認階段一已將機車資料寫入 PostGIS。

3. 執行融合：

   ```bash
   UV_CACHE_DIR=.uv-cache uv run python scripts/osm_tdx_fusion.py \
     --input-pbf data/raw/osm/taiwan-latest.osm.pbf \
     --output-pbf infra/valhalla/custom_files/taiwan_custom.pbf
   ```

腳本會先將目標區域道路暫存到 PostGIS，再透過文字與空間媒合：

- 將 `raw_tdx.motorcycle_waiting_zones` 對應到 OSM 路口節點，加入 `restriction:motorcycle=two_stage_turn`。
- 將 `raw_tdx.motorcycle_lane_restrictions` 對應到 OSM way，加入 `motorcycle:lanes=no|yes|yes`。
- 若整條道路皆禁行機車，加入標準 OSM `motorcycle=no`。

## 階段三：啟動 Valhalla

1. 確認融合後 PBF 存在：

   ```bash
   ls infra/valhalla/custom_files/taiwan_custom.pbf
   ```

2. 啟動 Valhalla：

   ```bash
   docker compose up -d valhalla
   docker compose logs -f valhalla
   ```

3. 驗證 route endpoint：

   ```bash
   bash scripts/valhalla_smoke_test.sh
   ```

4. 驗證 Meili 道路吸附：

   ```bash
   curl -X POST http://localhost:8002/trace_route \
     -H "Content-Type: application/json" \
     -d '{"shape":[{"lat":25.0337,"lon":121.5434},{"lat":25.0329,"lon":121.5410}],"costing":"motorcycle","shape_match":"map_snap"}'
   ```

原生 Valhalla 可以遵守標準 `motorcycle=no` 限制。兩段式左轉 `+90 秒` 懲罰仍需要依照 [valhalla-customization.md](valhalla-customization.md) 建立客製化映像。

## 階段四：啟動 Flutter App

1. 驗證 Flutter 專案：

   ```bash
   cd app/flutter_nav_mvp
   flutter pub get
   flutter analyze
   flutter test
   ```

2. 啟動 iOS 模擬器 App：

   ```bash
   flutter run \
     --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
     --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
   ```

3. Android 模擬器要改用 host loopback alias：

   ```bash
   flutter run \
     --dart-define=VALHALLA_BASE_URL=http://10.0.2.2:8002 \
     --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
   ```

4. App 啟動後：

   - 一般地圖只顯示底圖與定位。
   - 長按地圖上的目的地，進入路線預覽。
   - 確認距離與 ETA 後，按下開始進入導航。
   - 只有導航中才會顯示 maneuver、車道與虛擬待轉區。
   - 偏離路線超過門檻後，App 會自動呼叫 `/route` 重新規劃。

偏航判斷會優先使用 Meili 吸附位置，但只接受時間夠新且接近目前 raw GPS 的結果。過期吸附點或明顯定位跳點會退回 raw GPS，避免延遲重新規劃。MapLibre annotation 更新會依序執行，降低快速取消路線或連續選擇目的地時殘留舊線條的機率。

## 階段五：車道與虛擬待轉區

Flutter App 呼叫 Meili `/trace_route` 時會帶入 `turn_lanes: true`，並解析 `trip.legs[].maneuvers[].lanes`。

前端也能解析台灣機車管線提供的客製欄位：

- `motorcycle:lanes`：例如 `no|yes|yes`，供車道 UI 判斷禁行與可通行車道。
- `restriction:motorcycle=two_stage_turn`：可位於 maneuver 本身或 `custom`、`edge` 物件內。

當下一個兩段式左轉 maneuver 距離目前 GPS 小於 `50 公尺`，App 會在對應 shape point 繪製藍色半透明 MapLibre Polygon。

## TDX 可選流程

`scripts/tdx_ingest.py` 保留 TDX OAuth 與 endpoint 流程。如果未來取得適合的 TDX dataset：

1. 在 `.env` 填入 `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`。
2. 填入 `TDX_WAITING_ZONES_ENDPOINT`、`TDX_LANE_RESTRICTIONS_ENDPOINT`。
3. 執行：

   ```bash
   UV_CACHE_DIR=.uv-cache uv run python scripts/tdx_ingest.py --dataset all
   ```

MVP 現階段不需要 TDX 憑證即可執行。
