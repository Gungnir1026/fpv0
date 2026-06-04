# 更新紀錄

修改啟動、資料流程、測試方式或文件結構時，請在此追加紀錄。

```text
YYYY-MM-DD
- 異動：
- 指令：
- 驗證：
- 備註：
```

## 2026-06-04

- 異動：拆分 `navigation_map_page.dart`，將導航面板 UI 移至 `navigation_panels.dart`，MapLibre annotation 管理移至 `navigation_map_overlays.dart`。
- 驗證：`make test` 通過，包含 Python `unittest` 8 項、Python `compileall`、Compose config、Flutter analyze 與 Flutter 測試 30 項。
- 備註：此步為結構整理，未改變導航流程、路由請求或 UI 行為。

## 2026-06-04

- 異動：將 Valhalla Docker image 從 `latest` 固定為 digest `ghcr.io/valhalla/valhalla-scripted@sha256:2bafe8a908da3f538caabf867350d4e7c3dfb6e9a7e286bcf7a4cfa0f90b5e57`，對應 Valhalla `3.7.0` scripted image。
- 驗證：Compose 設定檢查、現有測試與 Valhalla `/route` smoke test。
- 備註：固定 digest 可避免相同 tag 重新發布造成路由服務行為漂移。

## 2026-06-04

- 異動：新增 `docs/architecture.md`、抽出 `docs/changelog.md`，並加入 Makefile 常用指令入口。
- 驗證：Markdown 文件清單、舊路徑引用檢查與 Makefile dry run。
- 備註：文件與操作入口整理，未修改 App 或 ETL 行為。

## 2026-06-04

- 異動：將日常啟停、技術棧與 Valhalla 客製化文件集中移至 `docs/`，並新增文件總目錄。
- 驗證：Markdown 文件清單與舊路徑引用檢查。
- 備註：根目錄保留 `README.md` 作為專案入口。

## 2026-05-31

- 異動：完成 P0 穩定性重構。將導航判斷抽離為 `NavigationGuidance`；Meili 吸附點僅在時間與距離皆合理時使用；取消 session 後忽略舊 Meili 錯誤；MapLibre annotation add、update、remove 改為依序執行。
- 驗證：Flutter 測試 30 項、`flutter analyze`、Python `unittest` 8 項、Python `compileall`、Compose config、Valhalla `/route` smoke test 與 iOS 模擬器重構前後畫面檢查全部通過。
- 備註：本機 `simctl` 不支援觸控注入，因此長按目的地、預覽與開始導航仍列為模擬器人工驗收步驟。

## 2026-05-31

- 異動：完成 roadmap P0。加入一般地圖、路線預覽與導航中三種 session；支援長按地圖選擇目的地、Valhalla `/route`、開始導航、導航中限定詳細資訊，以及偏航自動重新規劃。
- 驗證：Flutter 測試 24 項、`flutter analyze`、Python `unittest` 8 項、Python `compileall`、Compose config 與 Valhalla `/route` smoke test 全部通過。
- 備註：偏航距離優先使用 Meili 吸附位置，並以最短重新規劃間隔避免 GPS 飄移造成過度請求。

## 2026-05-31

- 異動：集中 Python `.env` 與 bbox 解析、清理 uv 專案設定、強化 GPS 欄位清理、polyline 解碼錯誤、Valhalla timeout、多 leg 幾何去重與 GPS 非同步佇列；新增 Python 與 Flutter 測試。
- 驗證：Python `unittest` 8 項、Flutter 測試 17 項、`flutter analyze`、Python `compileall`、Compose config 與 Valhalla smoke test 全部通過。
- 備註：新增 `docs/tech-stack.md` 與 `docs/roadmap.md`，並統一專案 Markdown 為繁體中文。

## 2026-05-31

- 異動：加入 GPS 座標驗證與 heading 正規化；一般地圖模式移除 Dart 主動 camera move，置中按鈕改用 MapLibre 原生定位追蹤。
- 驗證：`flutter analyze`、`flutter test` 與 iOS 模擬器啟動通過。
- 備註：iOS 模擬器可能回傳 `heading=-1`，不可直接傳入 native camera。

## 2026-05-25

- 異動：建立專案關閉、重設、啟動與測試清單。
- 驗證：文件更新。
- 備註：App 已可在 iOS 模擬器顯示臺北底圖與 Valhalla 路線。
