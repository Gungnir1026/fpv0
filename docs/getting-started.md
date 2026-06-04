# 專案啟停與重建步驟

本文件是日常啟動、完整關閉、全新建置、重建與測試的主要操作清單。資料流程的詳細說明請參考 [runbook.md](runbook.md)，歷史異動請參考 [changelog.md](changelog.md)。

## 目前服務

- PostGIS：容器 `tw-nav-postgis`，本機 port `5432`。
- Valhalla：容器 `tw-nav-valhalla`，本機 port `8002`。
- Python ETL：一律使用 `uv` 執行。
- Flutter App：位於 `app/flutter_nav_mvp`。
- 預設資料：臺北市開放資料加上 OSM PBF。

常用指令已整理在根目錄 `Makefile`。在專案根目錄執行 `make help` 可以查看後端啟動、資料匯入、測試與 App 啟動指令。

## 日常啟動

資料與 Valhalla 圖磚已經建置完成時，依序執行：

```bash
docker compose up -d postgis valhalla
curl http://localhost:8002/status
cd app/flutter_nav_mvp
flutter run \
  --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
  --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

iOS 模擬器若沒有位於臺北市，請設定測試座標：

```text
Features -> Location -> Custom Location...
Latitude: 25.0337
Longitude: 121.5434
```

## 完整關閉

1. 在執行 `flutter run` 的終端機按下：

   ```text
   q
   ```

   如果沒有停止，再按下 `Ctrl+C`。

2. 回到專案根目錄，停止容器並保留資料：

   ```bash
   docker compose down
   ```

3. 確認服務已停止：

   ```bash
   docker compose ps
   ```

`docker compose down` 不會刪除 PostGIS volume，也不會刪除 `infra/valhalla/custom_files` 內已建置的 Valhalla 檔案。

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
   docker compose up -d postgis
   ```

5. 使用 `uv` 安裝 Python 依賴：

   ```bash
   UV_CACHE_DIR=.uv-cache uv sync
   ```

6. 匯入臺北市開放資料：

   ```bash
   UV_CACHE_DIR=.uv-cache uv run python scripts/taipei_open_data_ingest.py --dataset all
   ```

7. 融合 OSM 與機車限制資料：

   ```bash
   UV_CACHE_DIR=.uv-cache uv run python scripts/osm_tdx_fusion.py \
     --input-pbf data/raw/osm/taiwan-latest.osm.pbf \
     --output-pbf infra/valhalla/custom_files/taiwan_custom.pbf
   ```

8. 啟動 Valhalla 並等待圖磚建置完成：

   ```bash
   docker compose up -d valhalla
   docker compose logs -f valhalla
   ```

   看到服務開始監聽 `8002` 後，以 `Ctrl+C` 離開 log 畫面即可。容器仍會繼續執行。

9. 驗證後端：

   ```bash
   bash scripts/valhalla_smoke_test.sh
   ```

10. 驗證 Flutter：

    ```bash
    cd app/flutter_nav_mvp
    flutter pub get
    flutter analyze
    flutter test
    ```

11. 啟動 iOS 模擬器 App：

    ```bash
    flutter run \
      --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
      --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
    ```

## 完整測試

在專案根目錄執行：

```bash
UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests/python -v
UV_CACHE_DIR=.uv-cache uv run python -m compileall -q scripts tests/python
docker compose config --quiet
bash scripts/valhalla_smoke_test.sh
cd app/flutter_nav_mvp
flutter analyze
flutter test
```

App 畫面應符合：

- 可看到臺北市街道底圖。
- 模擬器位置附近出現定位點。
- 一般地圖模式不顯示導航細節。
- 長按地圖上的另一個位置後，出現目的地 marker、路線與預覽面板。
- 預覽面板顯示距離、時間與開始按鈕。
- 按下開始後，畫面切換為導航中；只有此時才會顯示 maneuver、車道與虛擬待轉區。
- 導航中偏離規劃路線超過門檻時，App 會自動重新規劃。

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
docker compose up -d valhalla
docker compose logs -f valhalla
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
flutter run \
  --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
  --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

### Valhalla 回傳 HTTP 400

模擬器位置可能不在已建置的台灣圖資範圍內。將 iOS 模擬器位置設定為：

```text
Latitude: 25.0337
Longitude: 121.5434
```

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
flutter analyze
flutter test
```

目前一般地圖模式已避免由 Dart 主動建立 camera move，置中按鈕改用 MapLibre 原生定位追蹤，以避開 iOS 模擬器上的 native camera crash。

## 尚未完成

- Valhalla 兩段式左轉 `+90 秒` transition cost 客製化映像。
- 穩定將自訂 OSM 機車標籤輸出到 maneuver JSON 的後端整合。
- 可重複執行的待轉、禁行機車與偏航黃金路線整合測試。
