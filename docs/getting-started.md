# 專案啟停與重建步驟

本文件是日常啟動、完整關閉、全新建置、重建與測試的主要操作清單。資料流程的詳細說明請參考 [runbook.md](runbook.md)，歷史異動請參考 [changelog.md](changelog.md)。

## 目前服務

- PostGIS：容器 `tw-nav-postgis`，本機 port `5432`。
- Valhalla：容器 `tw-nav-valhalla`，本機 port `8002`。
- Python ETL：一律使用 `uv` 執行。
- Flutter App：位於 `app/flutter_nav_mvp`。
- 預設資料：臺北市開放資料加上 OSM PBF。

常用指令已整理在根目錄 `Makefile`。在專案根目錄執行 `make help` 可以查看後端啟動、資料匯入、測試與 App 啟動指令。

## Makefile 常用指令

| 指令 | 用途 |
| --- | --- |
| `make help` | 查看所有常用 target。 |
| `make postgis-up` | 只啟動 PostGIS；第一次建置、匯入資料與融合 OSM 時使用。 |
| `make valhalla-up` | 只啟動 Valhalla；已產生 `taiwan_custom.pbf` 後使用。 |
| `make backend-up` | 同時啟動 PostGIS 與 Valhalla；適合資料與圖磚已建置完成的日常啟動。 |
| `make backend-down` | 關閉後端容器並保留資料。 |
| `make backend-status` | 呼叫 Valhalla `/status`。 |
| `make backend-logs` | 追蹤 Valhalla log，等待圖磚建置或排查 smoke test。 |
| `make python-sync` | 使用 `uv` 安裝 Python 依賴。 |
| `make ingest-taipei` | 匯入臺北市開放資料。 |
| `make fuse-osm` | 融合 OSM 與機車限制資料，輸出 `taiwan_custom.pbf`。 |
| `make audit-pbf-tags` | 抽查融合後 PBF 是否含有待轉、車道與禁行機車標籤。 |
| `make test` | 執行不需要 Valhalla 已啟動的本機檢查。 |
| `make test-valhalla` | 驗證本機 Valhalla 能回傳大安區機車路線。 |
| `make test-golden-routes` | 執行大安區固定起訖點的 Valhalla 黃金路線驗收。 |
| `make test-valhalla-integration` | 驗證 `motorcycle=no` 會影響機車路由，並與 auto control 對照。 |
| `make route-facade-demo` | 呼叫 Valhalla 並補上 App 可解析的台灣機車語意欄位。 |
| `make app-ios` | 啟動 iOS 模擬器 App。 |
| `make app-android` | 啟動 Android 模擬器 App，會使用 `10.0.2.2` 連後端。 |

## 日常啟動

資料與 Valhalla 圖磚已經建置完成時，依序執行：

```bash
make backend-up
make backend-status
make app-ios
```

iOS 模擬器若沒有位於臺北市，請設定測試座標：

```text
Features -> Location -> Custom Location...
Latitude: 25.0337
Longitude: 121.5434
```

## 完整關閉

1. 在執行 `make app-ios`、`make app-android` 或底層 `flutter run` 的終端機按下：

   ```text
   q
   ```

   如果沒有停止，再按下 `Ctrl+C`。

2. 回到專案根目錄，停止容器並保留資料：

   ```bash
   make backend-down
   ```

3. 確認服務已停止：

   ```bash
   docker compose ps
   ```

`make backend-down` 底層會執行 `docker compose down`，不會刪除 PostGIS volume，也不會刪除 `infra/valhalla/custom_files` 內已建置的 Valhalla 檔案。

## 全新建置

適用於第一次啟動，或刻意清除資料後重新建立環境。

1. 確認本機工具：

   ```bash
   docker --version
   uv --version
   flutter --version
   ```

2. 建立本機環境設定：

   ```bash
   cp -n .env.example .env
   ```

   MVP 預設使用臺北市開放資料，因此 `TDX_*` 憑證與 endpoint 可以留白。

3. 準備 OSM PBF：

   ```text
   data/raw/osm/taiwan-latest.osm.pbf
   ```

4. 啟動 PostGIS：

   ```bash
   make postgis-up
   ```

5. 使用 `uv` 安裝 Python 依賴：

   ```bash
   make python-sync
   ```

6. 匯入臺北市開放資料：

   ```bash
   make ingest-taipei
   ```

7. 融合 OSM 與機車限制資料：

   ```bash
   make fuse-osm
   ```

8. 抽查融合後 PBF 內是否有機車標籤：

   ```bash
   make audit-pbf-tags
   ```

9. 啟動 Valhalla 並等待圖磚建置完成：

   ```bash
   make valhalla-up
   make backend-logs
   ```

   看到服務開始監聽 `8002` 後，以 `Ctrl+C` 離開 log 畫面即可。容器仍會繼續執行。

10. 驗證後端：

   ```bash
   make test-valhalla
   make test-golden-routes
   make test-valhalla-integration
   make route-facade-demo
   ```

11. 驗證 Flutter：

    ```bash
    make flutter-get
    make test-flutter
    ```

12. 啟動 iOS 模擬器 App：

    ```bash
    make app-ios
    ```

## 完整測試

在專案根目錄執行：

```bash
make test
make test-valhalla
make test-golden-routes
make test-valhalla-integration
make route-facade-demo
make audit-pbf-tags
```

App 畫面應符合：

- 可看到臺北市街道底圖。
- 模擬器位置附近出現定位點。
- 一般地圖模式不顯示導航細節。
- 長按地圖上的另一個位置後，出現目的地 marker、路線與預覽面板。
- 預覽面板顯示距離、時間與開始按鈕。
- 按下開始後，畫面切換為導航中；只有此時才會顯示 maneuver、車道與虛擬待轉區。
- 導航中偏離規劃路線超過門檻時，App 會自動重新規劃。
- `make test-golden-routes` 的三條大安區 baseline 路線皆通過。
- `make test-valhalla-integration` 顯示 auto control 會走 `民族陸橋`，motorcycle 會避開同一條 `motorcycle=no` 道路。
- `make route-facade-demo` 可輸出 App 可解析的 `taiwan_motorcycle`、`motorcycle:lanes` 與待轉語意欄位。
- `make audit-pbf-tags` 顯示待轉、車道與禁行機車標籤至少達到最低門檻。

偏航判斷會優先採用新鮮且接近目前 raw GPS 的 Meili 吸附點。如果吸附結果已過期，或定位突然跳離原位置，App 會退回 raw GPS，避免舊吸附點延遲重新規劃。

## 重建資料

### 只重建 Valhalla 圖磚

資料庫不變，只要求 Valhalla 根據現有 `taiwan_custom.pbf` 重新建立圖磚：

```bash
docker compose stop valhalla
rm -rf infra/valhalla/custom_files/taiwan_custom
rm -f infra/valhalla/custom_files/taiwan_custom.tar
rm -f infra/valhalla/custom_files/admins.sqlite
rm -f infra/valhalla/custom_files/timezones.sqlite
rm -f infra/valhalla/custom_files/file_hashes.txt
make valhalla-up
make backend-logs
```

### 完整清除

警告：以下指令會刪除 PostGIS volume。只有確定要從頭建立資料庫時才執行：

```bash
docker compose down -v
```

若也要清除 Valhalla 產物：

```bash
rm -rf infra/valhalla/custom_files/taiwan_custom
rm -f infra/valhalla/custom_files/taiwan_custom.tar
rm -f infra/valhalla/custom_files/taiwan_custom.pbf
rm -f infra/valhalla/custom_files/admins.sqlite
rm -f infra/valhalla/custom_files/timezones.sqlite
rm -f infra/valhalla/custom_files/file_hashes.txt
```

通常不要刪除原始 OSM PBF，否則必須重新下載：

```text
data/raw/osm/taiwan-latest.osm.pbf
```

## 常見問題

### 地圖有路線但沒有街道

啟動 Flutter 時帶入 OpenFreeMap 樣式：

```bash
make app-ios
```

Android 模擬器則使用：

```bash
make app-android
```

### Valhalla 回傳 HTTP 400

模擬器位置可能不在已建置的台灣圖資範圍內。將 iOS 模擬器位置設定為：

```text
Latitude: 25.0337
Longitude: 121.5434
```

### `make test-valhalla`、`make test-golden-routes` 或 `make test-valhalla-integration` 出現 Empty reply from server

Valhalla 可能仍在建置圖磚，或正在載入剛產生的 `taiwan_custom.pbf`。先執行：

```bash
make backend-logs
```

等待 log 顯示服務已開始監聽 `8002` 後，再重新執行後端驗收指令。

### App 無法連線後端

iOS 模擬器使用：

```bash
--dart-define=VALHALLA_BASE_URL=http://localhost:8002
```

Android 模擬器使用：

```bash
--dart-define=VALHALLA_BASE_URL=http://10.0.2.2:8002
```

### Flutter 顯示 Lost connection to device

如果 App 啟動後立即中斷，先保留終端機錯誤訊息，再執行：

```bash
make test-flutter
```

目前一般地圖模式已避免由 Dart 主動建立 camera move，置中按鈕改用 MapLibre 原生定位追蹤，以避開 iOS 模擬器上的 native camera crash。

## 尚未完成

- Valhalla 兩段式左轉 `+90 秒` transition cost 客製化映像。
- 長駐 API facade 或自訂 Valhalla service，讓 App 不必透過 CLI demo 才能取得台灣機車語意欄位。
- 可證明待轉 `+90 秒` 懲罰實際改變選路的 Valhalla 客製化整合測試。
