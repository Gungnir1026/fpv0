# 未來開發藍圖

## 目前狀態

目前 MVP 已打通「資料抓取、PostGIS 融合、Valhalla 路由、Flutter 地圖呈現」的基本鏈路。App 可以在 iOS 模擬器顯示臺北地圖、GPS 位置與 Meili 吸附路線，也已完成一般地圖、路線預覽、導航進行中三種 session 狀態。P0 穩定性整理已將導航判斷抽離為可測試 service，並加入吸附點新鮮度檢查與 MapLibre annotation 佇列。

P0 已完成。P1 的基礎驗收工具已補上：目前可以抽查融合後 PBF 的機車標籤，也可以用三條大安區黃金路線固定驗證 Valhalla baseline。下一個目標是將台灣機車限制真正寫入 Valhalla 圖磚與 costing，讓禁行機車與兩段式左轉懲罰確實影響選路。

## 優先順序

### P0：完成可操作的導航流程（已完成）

1. 建立三種 App 狀態：一般地圖、路線預覽、導航進行中。
2. 加入目的地選擇，先支援長按地圖設定目的地。
3. 呼叫 Valhalla `/route` 取得起點到終點的規劃路線。
4. 在預覽畫面顯示距離、預估時間與開始導航按鈕。
5. 只在導航進行中顯示車道級指引、下一個 maneuver 與虛擬待轉區。
6. 增加偏離路線偵測與重新規劃。

### P1：完成台灣機車路由語意

已完成：

1. 建立融合後 PBF 標籤抽查工具：`make audit-pbf-tags`。
2. 建立大安區 Valhalla baseline 黃金路線：`make test-golden-routes`。

下一步：

1. 以固定版本 Valhalla 原始碼建立自有映像。
2. 將 `restriction:motorcycle=two_stage_turn` 寫入圖磚可讀取的節點屬性。
3. 在機車左轉 transition cost 加入可設定的 `90 秒` 待轉懲罰。
4. 驗證 `motorcycle=no` 路段不可通行，且 `motorcycle:lanes=no|yes|yes` 可供前端顯示。
5. 將黃金路線擴充為禁行、待轉與一般左轉對照案例，證明客製化 costing 會改變選路。

### P2：服務化與營運品質

1. 在 App 與 Valhalla 之間加入 API facade，統一回傳 App 所需的導航 JSON。
2. 將資料更新流程改成可追蹤的批次作業，紀錄來源版本、執行時間與媒合統計。
3. 對地圖樣式、路由圖磚與交通資料建立版本編號。
4. 增加結構化日誌、錯誤追蹤與 API 延遲監控。
5. 評估離線向量圖磚與弱網路情境。

## 架構建議

Flutter 端建議逐步拆成三層：

| 層級 | 責任 |
| --- | --- |
| presentation | 地圖、路線預覽、導航面板、車道提示與互動狀態。 |
| domain | 導航 session、目的地、偏航、下一個 maneuver 與重新規劃規則。 |
| infrastructure | GPS、Valhalla API、MapLibre annotation 與本機快取。 |

後端建議增加輕量 API facade，避免 App 直接依賴 Valhalla 原始 JSON。facade 可整合路由結果、PostGIS 客製欄位與版本資訊，讓 Valhalla 升級時不需要同步修改 App。

## 效能方向

- ETL 只處理目標行政區與必要邊界，避免每次重建全台資料。
- 保留 PostGIS GiST index，並紀錄文字媒合與空間媒合命中率。
- GPS 更新維持節流與固定長度 trace buffer，避免頻繁呼叫 Meili。
- 為重新規劃加入最短間隔，避免 GPS 飄移造成 API 暴增。
- 將圖磚與資料版本寫入健康檢查，方便判斷 App 使用的路由資料是否過期。

## 資安方向

- `.env` 僅供本機使用，不得提交 TDX 憑證或正式資料庫密碼。
- 正式環境不得使用開發預設密碼，也不得讓 PostGIS 直接暴露於公網。
- App 對正式 API 應使用 HTTPS；`http://localhost:8002` 僅限本機模擬器測試。
- API facade 應加入驗證、rate limit、輸入範圍檢查與請求大小限制。
- 固定 Docker 映像、Python lockfile 與 Flutter 套件版本，並定期掃描依賴漏洞。

## 驗收里程碑

第一個可展示版本應完成：

1. 使用者可在地圖選擇目的地。
2. App 顯示路線預覽並可開始導航。
3. 導航中才顯示車道提示與兩段式左轉 UI。
4. 偏航後可以重新規劃。
5. 黃金路線測試可以證明禁行機車與待轉懲罰確實影響路徑選擇。
