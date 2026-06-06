UV_CACHE_DIR ?= .uv-cache
FLUTTER_DIR ?= app/flutter_nav_mvp
OSM_PBF ?= data/raw/osm/taiwan-latest.osm.pbf
CUSTOM_PBF ?= infra/valhalla/custom_files/taiwan_custom.pbf
GOLDEN_ROUTES ?= tests/golden_routes/daan_motorcycle_routes.json
VALHALLA_BASE_URL ?= http://localhost:8002
MAP_STYLE_URL ?= https://tiles.openfreemap.org/styles/liberty

.PHONY: help \
	postgis-up valhalla-up backend-up backend-down backend-status backend-logs \
	python-sync ingest-taipei fuse-osm \
	audit-pbf-tags test-python test-compose test-valhalla test-golden-routes test-flutter test \
	flutter-get flutter-analyze flutter-test app-ios app-android

help:
	@echo "常用指令："
	@echo "  make postgis-up       只啟動 PostGIS，適合第一次匯入與融合資料"
	@echo "  make valhalla-up      只啟動 Valhalla，適合 taiwan_custom.pbf 已產生後"
	@echo "  make backend-up       啟動 PostGIS 與 Valhalla"
	@echo "  make backend-down     關閉後端容器並保留資料"
	@echo "  make backend-status   檢查 Valhalla /status"
	@echo "  make backend-logs     追蹤 Valhalla log"
	@echo "  make python-sync      使用 uv 安裝 Python 依賴"
	@echo "  make ingest-taipei    匯入臺北市開放資料"
	@echo "  make fuse-osm         融合 OSM 與機車限制資料"
	@echo "  make audit-pbf-tags   抽查融合後 PBF 的機車標籤"
	@echo "  make test-python      執行 Python 測試與 compileall"
	@echo "  make test-flutter     執行 Flutter analyze 與 test"
	@echo "  make test             執行不需啟動 Valhalla 的本機檢查"
	@echo "  make test-valhalla    執行 Valhalla smoke test"
	@echo "  make test-golden-routes 執行 Valhalla 黃金路線測試"
	@echo "  make app-ios          啟動 iOS 模擬器 App"
	@echo "  make app-android      啟動 Android 模擬器 App"

postgis-up:
	docker compose up -d postgis

valhalla-up:
	docker compose up -d valhalla

backend-up:
	docker compose up -d postgis valhalla

backend-down:
	docker compose down

backend-status:
	curl $(VALHALLA_BASE_URL)/status

backend-logs:
	docker compose logs -f valhalla

python-sync:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync

ingest-taipei:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python scripts/taipei_open_data_ingest.py --dataset all

fuse-osm:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python scripts/osm_tdx_fusion.py --input-pbf $(OSM_PBF) --output-pbf $(CUSTOM_PBF)

audit-pbf-tags:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python scripts/pbf_tag_audit.py --pbf $(CUSTOM_PBF)

test-python:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m unittest discover -s tests/python -v
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python -m compileall -q scripts tests/python

test-compose:
	docker compose config --quiet

test-valhalla:
	bash scripts/valhalla_smoke_test.sh

test-golden-routes:
	UV_CACHE_DIR=$(UV_CACHE_DIR) uv run python scripts/valhalla_golden_routes.py --cases $(GOLDEN_ROUTES) --base-url $(VALHALLA_BASE_URL)

flutter-get:
	cd $(FLUTTER_DIR) && flutter pub get

flutter-analyze:
	cd $(FLUTTER_DIR) && flutter analyze

flutter-test:
	cd $(FLUTTER_DIR) && flutter test

test-flutter: flutter-analyze flutter-test

test: test-python test-compose test-flutter

app-ios:
	cd $(FLUTTER_DIR) && flutter run --dart-define=VALHALLA_BASE_URL=$(VALHALLA_BASE_URL) --dart-define=MAP_STYLE_URL=$(MAP_STYLE_URL)

app-android:
	cd $(FLUTTER_DIR) && flutter run --dart-define=VALHALLA_BASE_URL=http://10.0.2.2:8002 --dart-define=MAP_STYLE_URL=$(MAP_STYLE_URL)
