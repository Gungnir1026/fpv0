# 台灣機車導航 Flutter MVP

這個 Flutter App 是台灣機車導航 MVP 的前端。它會顯示 MapLibre 地圖、監聽 GPS 更新、呼叫 Valhalla `/route` 規劃路線，並將導航中的近期定位點送到 Meili `/trace_route` 做道路吸附。

App 也會解析 Valhalla maneuver 與 lane guidance。如果後端回傳台灣機車客製標記，前端可以顯示機車車道資訊，並在接近兩段式左轉路口時繪製虛擬待轉區。目前支援 maneuver 本身、`custom`、`edge` 與 `taiwan_motorcycle` 內的 `motorcycle:lanes`、`restriction:motorcycle=two_stage_turn` 與 `two_stage_turn_penalty_seconds`。

## 驗證

修改 Flutter 程式後，建議在專案根目錄執行：

```bash
make flutter-get
make test-flutter
```

若已位於本目錄，也可以直接執行底層 Flutter 指令：

```bash
flutter pub get
flutter analyze
flutter test
```

## 啟動

iOS 模擬器建議在專案根目錄使用：

```bash
make app-ios
```

Android 模擬器建議在專案根目錄使用：

```bash
make app-android
```

若已位於本目錄，iOS 模擬器使用：

```bash
flutter run \
  --dart-define=VALHALLA_BASE_URL=http://localhost:8002 \
  --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

Android 模擬器使用 host loopback alias：

```bash
flutter run \
  --dart-define=VALHALLA_BASE_URL=http://10.0.2.2:8002 \
  --dart-define=MAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty
```

## 原生建置需求

執行實機或模擬器測試前，請先確認：

```bash
flutter doctor -v
```

Android 專案目前需要：

- Android command-line tools。
- Flutter 相容的 JDK，例如 Java 17。
- Kotlin `2.1.0` 以上。
- `compileSdkVersion 35`。

iOS 專案需要完整 Xcode 與 iOS Simulator runtime。

## Android 權限

`android/app/src/main/AndroidManifest.xml` 已包含：

```xml
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.INTERNET" />
```

如果日後需要在背景持續導航，仍需依目標 Android SDK 增加 foreground service 與背景定位權限。

## iOS 權限

`ios/Runner/Info.plist` 已包含定位用途說明：

```xml
<key>NSLocationWhenInUseUsageDescription</key>
<string>Location is used to place the motorcycle on the navigation map.</string>
<key>NSLocationAlwaysAndWhenInUseUsageDescription</key>
<string>Location is used while navigating.</string>
```

## 主要檔案

| 檔案 | 用途 |
| --- | --- |
| `lib/src/widgets/navigation_map_page.dart` | MapLibre 地圖、GPS 追蹤、路線繪製與待轉區 overlay。 |
| `lib/src/widgets/lane_guidance_panel.dart` | 車道級導航提示。 |
| `lib/src/models/navigation_session.dart` | 一般地圖、路線預覽、導航進行中的 session 狀態。 |
| `lib/src/models/navigation_route.dart` | 路線幾何、ETA、距離與 maneuver。 |
| `lib/src/models/navigation_maneuver.dart` | maneuver、lane、機車車道權限與兩段式左轉解析。 |
| `lib/src/services/location_tracker.dart` | 定位權限與 GPS stream。 |
| `lib/src/services/valhalla_client.dart` | Valhalla `/route`、Meili `/trace_route`、timeout 與回應解析。 |
| `lib/src/services/navigation_guidance.dart` | 吸附點新鮮度、下一個 maneuver、車道與待轉提示判斷。 |
| `lib/src/services/polyline_codec.dart` | Valhalla polyline6 解碼。 |
| `lib/src/services/geo_math.dart` | 距離、偏航判斷與虛擬待轉區幾何運算。 |

## 目前互動模式

目前具備三種互動狀態：

1. 一般地圖：只顯示地圖與定位。
2. 路線預覽：長按地圖選擇目的地後，顯示目的地、路線、距離、ETA 與開始按鈕。
3. 導航進行中：顯示 maneuver、車道提示與兩段式左轉 overlay；偏航後自動重新規劃。

置中按鈕使用 MapLibre 原生定位追蹤，不由 Dart 主動建立 camera move，以避免 iOS 模擬器 native camera crash。

## 穩定性規則

- 偏航判斷只接受時間夠新且接近 raw GPS 的 Meili 吸附點，否則退回 raw GPS。
- 取消 navigation session 後，較晚回傳的舊 Meili 錯誤不會覆蓋一般地圖狀態。
- MapLibre annotation 的 add、update、remove 會依序執行，避免快速取消或連續長按目的地留下過期線條。
