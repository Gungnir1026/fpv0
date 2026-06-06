# 技術棧盤點

## 系統概觀

本專案採用「資料匯入與融合、路由服務、跨平台 App」三層架構：

1. Python ETL 將 OSM 與臺北市機車限制資料寫入 PostGIS，並輸出融合後的 PBF。
2. Valhalla 依照 PBF 建立路由圖磚，提供機車路由與 Meili 道路吸附 API。
3. Flutter App 使用 MapLibre 顯示地圖，取得 GPS 後呼叫 Valhalla 並繪製吸附路線。

## 資料來源

| 技術或資料源 | 用途 |
| --- | --- |
| OpenStreetMap PBF | 提供道路幾何、道路分類、路口節點與標籤，是 Valhalla 路由圖資的基礎。 |
| 臺北市資料大平臺 CSV | 提供機車待轉、禁行機車、例外可直接左轉與開放第三車道資料。MVP 預設使用此來源。 |
| 交通部 TDX API | 保留為可選資料來源。`scripts/tdx_ingest.py` 支援 OAuth 憑證、分頁抓取與 PostGIS 寫入。 |

## 後端與空間資料

| 技術 | 目前版本或映像 | 用途 |
| --- | --- | --- |
| PostgreSQL | Docker 映像 `postgis/postgis:16-3.5` 內建 PostgreSQL 16 | 儲存原始交通資料、融合暫存表與媒合結果。 |
| PostGIS | Docker 映像內建 PostGIS 3.5 | 執行道路、路口與限制資料的空間查詢與距離媒合。 |
| Valhalla | `ghcr.io/valhalla/valhalla-scripted@sha256:2bafe8a908da3f538caabf867350d4e7c3dfb6e9a7e286bcf7a4cfa0f90b5e57`，對應 Valhalla `3.7.0` scripted image | 建立路由圖磚，提供 `/route`、`/trace_route` 與 `/status`。 |
| Docker | `29.4.0` | 在本機隔離並啟動 PostGIS 與 Valhalla。 |
| Docker Compose | `v5.1.2` | 管理服務依賴、port、volume 與健康檢查。 |

Valhalla image 已固定到 digest，避免上游 `latest` 或相同 tag 重新發布造成不可預期差異。

## Python ETL

| 技術 | 目前版本 | 用途 |
| --- | --- | --- |
| Python | `3.12.12` | 執行資料抓取、正規化、空間融合與 PBF 改寫。 |
| uv | `0.11.17` | 管理 Python 虛擬環境、鎖定套件版本與執行腳本。 |
| requests | `2.34.2` | 呼叫臺北市開放資料與 TDX HTTP API。 |
| psycopg2-binary | `2.9.12` | 將資料寫入 PostgreSQL/PostGIS，並執行空間查詢。 |
| osmium | `4.3.1` | 讀取、篩選與改寫 OSM PBF。 |

Python 依賴以 `pyproject.toml` 與 `uv.lock` 為唯一來源。日常操作優先使用根目錄 `Makefile`，需要直接執行 Python 腳本時才使用 `uv run`。

## Flutter App

| 技術 | 目前版本 | 用途 |
| --- | --- | --- |
| Flutter | `3.44.0` stable | 建立 iOS 與 Android 共用介面。 |
| Dart | `3.12.0` | Flutter App 程式語言。 |
| maplibre_gl | `0.26.1` | 顯示向量地圖、定位點、吸附路線與虛擬待轉區 Polygon。 |
| geolocator | `14.0.2` | 處理定位權限、取得目前位置與監聽 GPS 更新。 |
| http | `1.6.0` | 呼叫 Valhalla `/route` 與 Meili `/trace_route`。 |

## 原生開發環境

| 技術 | 目前版本 | 用途 |
| --- | --- | --- |
| Xcode | `26.2`，Build `17C52` | 編譯與執行 iOS App。 |
| iOS Simulator | iOS `26.3` | 在不使用實機的情況下模擬 GPS 與驗證地圖畫面。 |
| Android Gradle/Kotlin 專案殼層 | 由 Flutter 產生 | 提供 Android 編譯入口；正式驗證前仍需完成本機 Android command-line tools 設定。 |

## 測試與品質工具

| 工具 | 用途 |
| --- | --- |
| `Makefile` | 封裝後端啟停、Python ETL、Flutter 驗證與 App 啟動；可用 `make help` 查看 target。 |
| `make test` | 執行 Python `unittest`、`compileall`、Compose config、Flutter analyze 與 Flutter test。 |
| `make test-valhalla` | 驗證本機 Valhalla 能回傳大安區機車路線；需要 Valhalla 已啟動且圖磚建置完成。 |
| `make test-golden-routes` | 以固定大安區起訖點驗證 Valhalla baseline 路線距離、時間、maneuver 與道路名稱。 |
| `make audit-pbf-tags` | 抽查融合後 PBF 是否含有台灣機車限制標籤。 |
| `flutter analyze` | 檢查 Dart 型別、lint 與常見程式品質問題。 |
| `flutter test` | 驗證 GPS 清理、polyline 解碼、車道解析、Valhalla client、導航 session、吸附點新鮮度、偏航幾何運算與 App 殼層。 |
| Python `unittest` | 驗證 `.env` 讀取、bbox 解析、路名拆分與機車車道限制正規化。 |
| `compileall` | 檢查 Python 腳本是否可編譯。 |
| `docker compose config --quiet` | 驗證 Compose 設定。 |
| `scripts/valhalla_smoke_test.sh` | 驗證本機 Valhalla 能回傳大安區機車路線。 |
