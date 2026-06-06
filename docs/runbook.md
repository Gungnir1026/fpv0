# 台灣機車導航 MVP 操作手冊

本文件說明資料管線與各階段操作方式。日常啟停請優先參考 [getting-started.md](getting-started.md)。

除非需要排查底層指令，操作時優先使用根目錄 `Makefile`。可先執行 `make help` 查看完整 target。

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
   make postgis-up
   ```

4. 使用 `uv` 安裝 Python 依賴：

   ```bash
   make python-sync
   ```

5. 將臺北市資料匯入 PostGIS：

   ```bash
   make ingest-taipei
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
   make fuse-osm
   ```

4. 抽查融合後 PBF 的機車標籤：

   ```bash
   make audit-pbf-tags
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
   make valhalla-up
   make backend-logs
   ```

3. 驗證 route endpoint：

   ```bash
   make test-valhalla
   ```

4. 驗證固定黃金路線：

   ```bash
   make test-golden-routes
   ```

   黃金路線案例位於 `tests/golden_routes/daan_motorcycle_routes.json`，目前固定檢查三組大安區起訖點的距離、時間、maneuver 數量與必要道路名稱。

5. 驗證機車語意整合案例：

   ```bash
   make test-valhalla-integration
   ```

   整合案例位於 `tests/integration/valhalla_motorcycle_semantics.json`。目前包含 `民族陸橋` control：auto 會通過該道路，motorcycle 會因 `motorcycle=no` 避開。

6. 驗證 API facade 可回傳 App 可解析的台灣機車語意：

   ```bash
   make test-facade
   make route-facade-demo
   ```

   `make test-facade` 會啟動測試用 facade server，呼叫 `/health`、`/route` 與 `/trace_route`，確認 route 回應含有 `taiwan_motorcycle` 與 `motorcycle:lanes`。`make route-facade-demo` 保留 CLI 形式，方便直接檢視完整 JSON。

7. 驗證 Meili 道路吸附：

   ```bash
   curl -X POST http://localhost:8010/trace_route \
     -H "Content-Type: application/json" \
     -d '{"shape":[{"lat":25.0337,"lon":121.5434},{"lat":25.0329,"lon":121.5410}],"costing":"motorcycle","shape_match":"map_snap"}'
   ```

原生 Valhalla 可以遵守標準 `motorcycle=no` 限制。facade 目前會補上台灣機車語意欄位，但兩段式左轉 `+90 秒` 懲罰仍需要依照 [valhalla-customization.md](valhalla-customization.md) 建立客製化映像。

## 階段四：啟動 Flutter App

1. 驗證 Flutter 專案：

   ```bash
   make flutter-get
   make test-flutter
   ```

2. 啟動 iOS 模擬器 App：

   ```bash
   make facade-up
   ```

   `make facade-up` 會持續執行。另開一個終端機：

   ```bash
   make app-ios
   ```

3. Android 模擬器要改用 host loopback alias：

   ```bash
   make app-android
   ```

4. App 啟動後：

   - 一般地圖只顯示底圖與定位。
   - 長按地圖上的目的地，進入路線預覽。
   - 確認距離與 ETA 後，按下開始進入導航。
   - 只有導航中才會顯示 maneuver、車道與虛擬待轉區。
   - 偏離路線超過門檻後，App 會自動呼叫 facade `/route` 重新規劃。

偏航判斷會優先使用 Meili 吸附位置，但只接受時間夠新且接近目前 raw GPS 的結果。過期吸附點或明顯定位跳點會退回 raw GPS，避免延遲重新規劃。MapLibre annotation 更新會依序執行，降低快速取消路線或連續選擇目的地時殘留舊線條的機率。

## 階段五：車道與虛擬待轉區

Flutter App 呼叫 facade `/trace_route` 時會帶入 `turn_lanes: true`，facade 會透明代理到 Meili，App 會解析 `trip.legs[].maneuvers[].lanes`。

前端也能解析台灣機車管線提供的客製欄位：

- `motorcycle:lanes`：例如 `no|yes|yes`，供車道 UI 判斷禁行與可通行車道。
- `restriction:motorcycle=two_stage_turn`：可位於 maneuver 本身或 `custom`、`edge`、`taiwan_motorcycle` 物件內。
- `taiwan_motorcycle.two_stage_turn=true` 與 `taiwan_motorcycle.two_stage_turn_penalty_seconds=90`：供 UI 顯示與後續客製 Valhalla costing 驗證使用；目前尚未改變 stock Valhalla costing。

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
