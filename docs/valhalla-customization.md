# Valhalla 機車成本客製化設計

## 原生 Valhalla 已支援的限制

融合後的 PBF 使用標準 OSM access 標籤表示硬性限制。當 way 帶有：

```text
motorcycle=no
```

Valhalla 建置圖磚時會產生 access flag，`motorcycle` costing 便能排除該道路。

目前已用 `make test-valhalla-integration` 驗證：auto control 會走 `民族陸橋`，而 motorcycle route 會避開同一條 `motorcycle=no` 道路。

車道級標籤：

```text
motorcycle:lanes=no|yes|yes
```

目前保留給前端顯示與後續圖磚屬性擴充。只要道路仍有一條可合法通行的車道，原生 Valhalla 不應將整條 edge 排除。

目前 `scripts/taiwan_motorcycle_api.py` 可從融合後 PBF 推導 `motorcycle:lanes`，並補回 Valhalla maneuver 的 `taiwan_motorcycle` 與 `custom` 欄位，Flutter parser 已可解析此格式。`scripts/taiwan_motorcycle_route_facade.py` 仍保留為 CLI demo。

## 兩段式左轉為何需要修改引擎

`restriction:motorcycle=two_stage_turn` 是本 MVP 新增的語意。Valhalla 在 Mjolnir 建置階段會將 OSM 標籤轉成緊湊圖磚結構；Sif costing 在路由階段讀取的是圖磚屬性，不會直接讀取原始 OSM 任意標籤。

要實作真正的 `+90 秒` 懲罰，需要同時修改：

1. Mjolnir：遇到 `restriction:motorcycle=two_stage_turn` 節點時，寫入可供圖磚保存的路口 flag。
2. Sif：`MotorcycleCost::TransitionCost` 在機車左轉通過該節點時增加 `90 秒`。

目前 API facade 與 `make route-facade-demo` 只會把 `two_stage_turn_penalty_seconds=90` 作為語意欄位補回 response，方便 UI 與後續客製 Valhalla 驗證；它尚未改變 stock Valhalla 的選路與 ETA。

## 目標行為

- 硬性規則：`motorcycle=no` edge 絕對不可通行。
- 軟性規則：帶有兩段式左轉 flag 的左轉增加 `Cost(90, 90)`，同時影響選路與 ETA。
- 同一路口的直行與右轉不應被懲罰。
- 懲罰秒數應可透過 costing option 設定。

## 實作輪廓

Valhalla 內部圖磚 struct 大小固定，而且不同版本可能變動。請先固定 Valhalla release，再針對該版本實作與測試。

1. 在 `valhalla/baldr/nodeinfo.h` 或 `valhalla/baldr/graphconstants.h` 增加節點 flag 或 node type。

   ```cpp
   // 僅為結構示意。固定版本後，優先使用尚未占用的 flag。
   enum class NodeType : uint8_t {
     // 既有值...
     kMotorcycleTwoStageTurn = 15
   };
   ```

2. 在 Mjolnir OSM node parser 偵測融合標籤：

   ```cpp
   const auto two_stage =
       tags.find("restriction:motorcycle") != tags.end() &&
       tags.at("restriction:motorcycle") == "two_stage_turn";
   ```

3. 建立 graph node 時保存 flag：

   ```cpp
   if (two_stage) {
     nodeinfo.set_type(NodeType::kMotorcycleTwoStageTurn);
   }
   ```

4. 在 `src/sif/motorcyclecost.cc` 增加可設定懲罰，並套用到 `MotorcycleCost::TransitionCost`：

   ```cpp
   constexpr float kDefaultTwoStageTurnPenalty = 90.0f;

   Cost MotorcycleCost::TransitionCost(
       const baldr::DirectedEdge* edge,
       const baldr::NodeInfo* node,
       const EdgeLabel& pred,
       const graph_tile_ptr& tile,
       const std::function<LimitedGraphReader()>& reader_getter) const {
     auto cost = BaseTransitionCost(edge, node, pred, tile, reader_getter);

     if (node->type() == NodeType::kMotorcycleTwoStageTurn &&
         IsLeftTurn(edge, pred, tile, reader_getter)) {
       cost.cost += two_stage_turn_penalty_;
       cost.secs += two_stage_turn_penalty_;
     }

     return cost;
   }
   ```

5. 如果使用雙向或反向搜尋，也要加入 reverse transition costing。

6. 支援 costing option：

   ```json
   {
     "costing": "motorcycle",
     "costing_options": {
       "motorcycle": {
         "two_stage_turn_penalty": 90
       }
     }
   }
   ```

## 客製映像建置

P1 scaffold 位於 `infra/valhalla/custom/README.md`。固定 Valhalla release 並套用 patch 後：

```bash
git clone https://github.com/valhalla/valhalla.git vendor/valhalla
cd vendor/valhalla
git checkout 3.7.0
# 依照固定版本調整程式，並提交或保存 patch。
docker build -f docker/Dockerfile-scripted -t tw-nav-valhalla:two-stage-turn .
```

接著修改 `docker-compose.yml`：

```yaml
valhalla:
  image: tw-nav-valhalla:two-stage-turn
```

## 測試要求

客製引擎至少要加入：

- `motorcycle=no` 路段不可通行。
- 有待轉 flag 的左轉 cost 與 ETA 增加 `90 秒`。
- 同路口直行與右轉不增加懲罰。
- 開啟與關閉懲罰時，黃金路線選擇符合預期。
- `make test-valhalla-integration`、`make test-golden-routes`、`make test-facade` 與 `make route-facade-demo` 仍維持可用。

## 暫時性替代方案

不建議預設啟用。若將待轉節點暫時編碼成既有 toll 或 gate 類型，再套用 `90 秒` 成本，雖然可減少 C++ schema 修改，但會錯誤懲罰該路口的所有行進方向，也會污染原始語意，不適合正式導航品質。
