# Valhalla P1 客製化 Scaffold

此目錄保存 P1 後端語意實作的客製化契約與後續 C++ patch 入口。專案目前仍使用 `docker-compose.yml` 中固定 digest 的 stock Valhalla scripted image；此 scaffold 尚未被 Compose 啟用。

## 目前已落地

- `motorcycle=no`：透過標準 OSM access tag 寫入融合後 PBF，並以 `make test-valhalla-integration` 驗證機車路由會避開 `民族陸橋`，而 auto control 會通過同一條道路。
- `motorcycle:lanes`：保留在融合後 PBF，並可由 `scripts/taiwan_motorcycle_route_facade.py` 推導為 maneuver 的 `taiwan_motorcycle.motorcycle:lanes`，供 Flutter 車道 UI 使用。
- `restriction:motorcycle=two_stage_turn`：保留在融合後 PBF，facade 可推導為 maneuver 的 `taiwan_motorcycle.two_stage_turn=true` 與 `two_stage_turn_penalty_seconds=90`。

## 尚未落地

兩段式左轉 `+90 秒` 尚未進入 Valhalla Sif costing。也就是說，facade 與 Flutter 能顯示待轉語意，但 stock Valhalla 的選路與 ETA 還不會因待轉懲罰改變。

## C++ 實作契約

後續真正客製 Valhalla 時需完成：

1. Mjolnir 在讀取 OSM node 時辨識 `restriction:motorcycle=two_stage_turn`。
2. Graph tile 中保留可供 Sif 讀取的 two-stage-turn node flag。
3. `MotorcycleCost` 讀取 costing option：

   ```json
   {
     "costing_options": {
       "motorcycle": {
         "two_stage_turn_penalty": 90
       }
     }
   }
   ```

4. 機車左轉 transition 通過 two-stage-turn node 時，對 `Cost.cost` 與 `Cost.secs` 增加同一個懲罰秒數。
5. 直行、右轉與非機車 costing 不套用此懲罰。
6. `make test-golden-routes` 與 `make test-valhalla-integration` 必須持續通過；後續需再新增開啟/關閉懲罰會改變選路的對照案例。

## 建置策略

正式 patch 前不要把此 scaffold 接進 Compose。等 C++ patch 可以穩定 build 後，再新增自有 image，例如：

```bash
docker build -f infra/valhalla/custom/Dockerfile -t tw-nav-valhalla:two-stage-turn .
```

然後將 `docker-compose.yml` 的 Valhalla image 切到自有 image，並重建 `taiwan_custom.tar`。
