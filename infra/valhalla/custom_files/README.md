# Valhalla 客製檔案目錄

Valhalla scripted Docker 映像會從此掛載目錄讀取：

- OSM PBF。
- `valhalla.json`。
- 編譯後路由圖磚。
- timezone、admins 與 tar 等支援檔案。

OSM 與臺北市資料融合後，`scripts/osm_tdx_fusion.py` 會輸出：

```text
taiwan_custom.pbf
```

啟動 Valhalla 容器後，scripted 映像會根據 PBF 與設定檔產生圖磚。產生的資料屬於本機建置產物，不應提交版本控制。

兩段式左轉 `+90 秒` 成本仍需要自有 Valhalla 映像，請參考 [valhalla-customization.md](../../../docs/valhalla-customization.md)。
