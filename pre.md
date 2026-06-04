他人 pull repo 後，**還缺的是本機環境與大型資料**。GitHub 上不會放 OSM PBF、Valhalla 圖磚、`.env`、build cache。

**需要先安裝**

- Docker Desktop 或 OrbStack
- `uv`
- Flutter
- iOS 測試需要 Xcode + iOS Simulator
- Android 測試需要 Android Studio / emulator

**需要準備的資料**
最重要的是 OSM PBF：

```text
data/raw/osm/taiwan-latest.osm.pbf
```

這個檔案沒有放 GitHub，因為約數百 MB。可以從 Geofabrik 下載 Taiwan OSM PBF，或由你提供給同學。

臺北市開放資料不用手動準備，腳本會自動下載。

**第一次啟動流程**
在 repo 根目錄：

```bash
cp .env.example .env
mkdir -p data/raw/osm
```

把 `taiwan-latest.osm.pbf` 放到：

```text
data/raw/osm/taiwan-latest.osm.pbf
```

接著：

```bash
docker compose up -d postgis
make python-sync
make ingest-taipei
make fuse-osm
docker compose up -d valhalla
make test-valhalla
```

Flutter：

```bash
cd app/flutter_nav_mvp
flutter pub get
flutter analyze
flutter test
```

啟動 iOS 模擬器 App：

```bash
cd ../..
make app-ios
```

**如果只是要快速展示**
你可以直接給同學這幾個本機資料檔，省掉 ETL：

```text
data/raw/osm/taiwan-latest.osm.pbf
infra/valhalla/custom_files/taiwan_custom.pbf
infra/valhalla/custom_files/taiwan_custom.tar
infra/valhalla/custom_files/taiwan_custom/
infra/valhalla/custom_files/admins.sqlite
infra/valhalla/custom_files/timezones.sqlite
```

但這些不要放 GitHub，適合用雲端硬碟或 GitHub Release。

**最短說法**
他人 pull 後還需要：

1. 安裝 Docker、uv、Flutter、Xcode。
2. 複製 `.env.example` 成 `.env`。
3. 準備 `data/raw/osm/taiwan-latest.osm.pbf`。
4. 跑 `make python-sync`、匯入臺北資料、融合 OSM。
5. 啟動 Valhalla。
6. 跑 Flutter App。
