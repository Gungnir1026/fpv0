# 台灣機車導航 MVP

本專案是一套針對台灣道路情境設計的機車導航最小可行性產品。資料管線會將 OpenStreetMap（OSM）PBF 與臺北市開放資料融合，建立 Valhalla 路由圖資，再由 Flutter App 透過 MapLibre 顯示地圖、GPS 定位與 Meili 道路吸附結果。

目前測試範圍鎖定臺北市大安區，並已具備：

- 臺北市機車待轉、禁行機車與開放第三車道資料匯入。
- OSM 道路與機車限制資料融合。
- PostGIS 空間媒合。
- Valhalla 機車路由與 Meili `/trace_route` 道路吸附。
- Flutter iOS 模擬器地圖、定位、吸附路線、車道資訊解析與虛擬待轉區繪製。
- 一般地圖、路線預覽、導航進行中三種 session 狀態。
- 長按地圖選擇目的地、Valhalla `/route` 規劃與偏航自動重新規劃。
- Meili 吸附點新鮮度檢查與 MapLibre annotation 佇列，降低 GPS 飄移與快速操作造成的競態。

## 快速啟動

如果資料已經完成建置，只需：

```bash
docker compose up -d postgis valhalla
curl http://localhost:8002/status
cd app/flutter_nav_mvp
flutter run \
  --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
  --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

如果是第一次啟動，請依照 [docs/getting-started.md](docs/getting-started.md) 的「全新建置」執行。

## 文件索引

- [docs/README.md](docs/README.md)：所有文件的用途與閱讀順序。
- [docs/architecture.md](docs/architecture.md)：資料格式、資料流、服務邊界、路由流程與目前規則生效狀態。
- [docs/getting-started.md](docs/getting-started.md)：每日啟停、全新建置、重建與常見問題。
- [docs/runbook.md](docs/runbook.md)：資料管線與各階段操作手冊。
- [docs/tech-stack.md](docs/tech-stack.md)：技術棧、版本與用途。
- [docs/roadmap.md](docs/roadmap.md)：後續功能、架構、效能與資安規劃。
- [docs/valhalla-customization.md](docs/valhalla-customization.md)：Valhalla 兩段式左轉 `+90 秒` 成本客製化設計。
- [docs/changelog.md](docs/changelog.md)：專案整理、功能與驗證紀錄。

## 專案結構

```text
.
├── app/flutter_nav_mvp/          # Flutter + MapLibre App
├── data/raw/                     # 本機下載資料，不納入版本控制
├── docs/                         # 文件索引、操作手冊、技術棧與開發藍圖
├── infra/postgres/init/          # PostGIS 初始化 SQL
├── infra/valhalla/               # Valhalla 設定與本機圖磚建置目錄
├── scripts/                      # Python 資料匯入、融合與 smoke test
├── tests/python/                 # Python 單元測試
├── docker-compose.yml            # PostGIS 與 Valhalla 服務
├── Makefile                      # 常用開發、測試與啟動指令
└── pyproject.toml                # uv 管理的 Python 專案設定
```

## 驗證指令

```bash
UV_CACHE_DIR=.uv-cache uv run python -m unittest discover -s tests/python -v
UV_CACHE_DIR=.uv-cache uv run python -m compileall -q scripts tests/python
docker compose config --quiet
bash scripts/valhalla_smoke_test.sh
cd app/flutter_nav_mvp
flutter analyze
flutter test
```

也可以使用 Makefile 包裝後的常用指令：

```bash
make test-python
make test-flutter
make backend-up
make app-ios
```
