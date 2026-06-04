import 'package:maplibre_gl/maplibre_gl.dart';

import '../models/gps_sample.dart';
import '../models/navigation_route.dart';
import '../services/geo_math.dart';

class NavigationMapOverlays {
  static const _routeColor = '#0077b6';
  static const _rawGpsColor = '#ef476f';
  static const _destinationColor = '#d62828';
  static const _twoStageTurnFillColor = '#168aad';
  static const _twoStageTurnOutlineColor = '#0353a4';

  MapLibreMapController? _controller;
  bool _styleLoaded = false;

  Line? _plannedRouteLine;
  Circle? _rawGpsCircle;
  Circle? _destinationCircle;
  Fill? _twoStageTurnFill;

  void setController(MapLibreMapController controller) {
    _controller = controller;
  }

  void clearController() {
    _controller = null;
    _styleLoaded = false;
    _plannedRouteLine = null;
    _rawGpsCircle = null;
    _destinationCircle = null;
    _twoStageTurnFill = null;
  }

  Future<void> resetAfterStyleLoaded({
    required GpsSample? rawSample,
    required LatLng? destination,
    required NavigationRoute? route,
    required bool navigating,
    required LatLng? twoStageTurnPoint,
  }) async {
    _styleLoaded = true;
    _plannedRouteLine = null;
    _rawGpsCircle = null;
    _destinationCircle = null;
    _twoStageTurnFill = null;

    if (rawSample != null) {
      await drawRawGps(rawSample);
    }
    await drawDestination(destination);
    await drawPlannedRoute(route, navigating: navigating);
    await updateTwoStageTurn(twoStageTurnPoint);
  }

  Future<void> drawRawGps(GpsSample sample) async {
    final controller = _controller;
    if (!_styleLoaded || controller == null) {
      return;
    }

    final options = CircleOptions(
      geometry: sample.latLng,
      circleRadius: 6,
      circleColor: _rawGpsColor,
      circleStrokeWidth: 2,
      circleStrokeColor: '#ffffff',
    );

    if (_rawGpsCircle == null) {
      _rawGpsCircle = await controller.addCircle(options);
    } else {
      await controller.updateCircle(_rawGpsCircle!, options);
    }
  }

  Future<void> drawDestination(LatLng? destination) async {
    final controller = _controller;
    if (!_styleLoaded || controller == null || destination == null) {
      return;
    }

    final options = CircleOptions(
      geometry: destination,
      circleRadius: 8,
      circleColor: _destinationColor,
      circleStrokeWidth: 3,
      circleStrokeColor: '#ffffff',
    );

    if (_destinationCircle == null) {
      _destinationCircle = await controller.addCircle(options);
    } else {
      await controller.updateCircle(_destinationCircle!, options);
    }
  }

  Future<void> removeDestination() async {
    final controller = _controller;
    final circle = _destinationCircle;
    if (controller == null || circle == null) {
      return;
    }

    await controller.removeCircle(circle);
    _destinationCircle = null;
  }

  Future<void> drawPlannedRoute(
    NavigationRoute? route, {
    required bool navigating,
  }) async {
    final controller = _controller;
    if (!_styleLoaded || controller == null || route?.hasGeometry != true) {
      return;
    }

    final options = LineOptions(
      geometry: route!.geometry,
      lineColor: _routeColor,
      lineOpacity: navigating ? 0.96 : 0.8,
      lineWidth: navigating ? 6 : 5,
    );

    if (_plannedRouteLine == null) {
      _plannedRouteLine = await controller.addLine(options);
    } else {
      await controller.updateLine(_plannedRouteLine!, options);
    }
  }

  Future<void> clearPlannedRoute() async {
    final controller = _controller;
    final line = _plannedRouteLine;
    if (controller == null || line == null) {
      return;
    }

    await controller.removeLine(line);
    _plannedRouteLine = null;
  }

  Future<void> updateTwoStageTurn(LatLng? point) async {
    final controller = _controller;
    if (!_styleLoaded || controller == null) {
      return;
    }
    if (point == null) {
      await removeTwoStageTurn();
      return;
    }

    final options = FillOptions(
      geometry: [
        GeoMath.squareAround(point),
      ],
      fillColor: _twoStageTurnFillColor,
      fillOpacity: 0.28,
      fillOutlineColor: _twoStageTurnOutlineColor,
    );

    if (_twoStageTurnFill == null) {
      _twoStageTurnFill = await controller.addFill(options);
    } else {
      await controller.updateFill(_twoStageTurnFill!, options);
    }
  }

  Future<void> removeTwoStageTurn() async {
    final controller = _controller;
    final fill = _twoStageTurnFill;
    if (controller == null || fill == null) {
      return;
    }

    await controller.removeFill(fill);
    _twoStageTurnFill = null;
  }

  Future<void> centerOnLatestPosition() async {
    final controller = _controller;
    if (controller == null) {
      return;
    }

    await controller.updateMyLocationTrackingMode(
      MyLocationTrackingMode.tracking,
    );
  }
}
