# 文件導覽

本文件是專案文件的總目錄。根目錄 [README.md](../README.md) 保持簡短，適合快速理解專案；更細的操作、架構與後續規劃則集中在 `docs/`。

## 建議閱讀順序

1. [getting-started.md](getting-started.md)：第一次建置、日常啟動、關閉、重建與常見問題。想把專案跑起來，先看這份。
2. [architecture.md](architecture.md)：資料格式、資料流、服務邊界、路由流程與目前規則生效狀態。想理解專案怎麼串起來，看這份。
3. [runbook.md](runbook.md)：資料匯入、OSM 融合、Valhalla 啟動、Flutter 驗證與 TDX 可選流程。需要重跑資料管線時看這份。
4. [tech-stack.md](tech-stack.md)：列出專案使用的框架、資料庫、套件、工具與用途。適合介紹技術選型。
5. [roadmap.md](roadmap.md)：目前完成狀態、P1/P2 優先事項、架構建議、效能與資安方向。適合規劃下一步。
6. [valhalla-customization.md](valhalla-customization.md)：說明兩段式左轉 `+90 秒` 成本為什麼需要客製 Valhalla，以及預期修改位置。
7. [changelog.md](changelog.md)：專案整理、功能與驗證紀錄。

## 其他 Markdown

| 文件 | 功能 |
| --- | --- |
| [../README.md](../README.md) | 專案首頁，包含專案摘要、快速啟動、文件索引與專案結構。 |
| [../Makefile](../Makefile) | 常用開發指令入口，包裝後端啟動、資料匯入、測試與 Flutter 啟動。 |
| [../app/flutter_nav_mvp/README.md](../app/flutter_nav_mvp/README.md) | Flutter App 子專案說明，包含驗證、啟動、iOS/Android 權限與主要檔案。 |
| [../infra/valhalla/custom/README.md](../infra/valhalla/custom/README.md) | Valhalla P1 客製化 scaffold，說明 `motorcycle=no`、facade 語意與兩段式左轉 C++ 成本契約。 |
| [../infra/valhalla/custom_files/README.md](../infra/valhalla/custom_files/README.md) | Valhalla 掛載目錄說明，標示哪些檔案是本機建置產物。 |
| [../app/flutter_nav_mvp/ios/Runner/Assets.xcassets/LaunchImage.imageset/README.md](../app/flutter_nav_mvp/ios/Runner/Assets.xcassets/LaunchImage.imageset/README.md) | Flutter/iOS 產生的啟動畫面資產說明，通常不需要手動維護。 |

## 維護原則

- 操作步驟放在 [getting-started.md](getting-started.md) 或 [runbook.md](runbook.md)，避免塞進根目錄 README。
- 架構、資料格式與服務邊界放在 [architecture.md](architecture.md)。
- 技術選型與版本更新放在 [tech-stack.md](tech-stack.md)。
- 未來功能、優先順序與風險放在 [roadmap.md](roadmap.md)。
- Valhalla C++ 成本客製化集中在 [valhalla-customization.md](valhalla-customization.md)。
- 歷史異動集中在 [changelog.md](changelog.md)。
