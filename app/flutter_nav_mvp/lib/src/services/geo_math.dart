import 'dart:math' as math;

import 'package:maplibre_gl/maplibre_gl.dart';

class GeoMath {
  const GeoMath._();

  static const earthRadiusMeters = 6371008.8;

  static double distanceMeters(LatLng a, LatLng b) {
    final lat1 = _radians(a.latitude);
    final lat2 = _radians(b.latitude);
    final deltaLat = _radians(b.latitude - a.latitude);
    final deltaLon = _radians(b.longitude - a.longitude);

    final haversine = math.sin(deltaLat / 2) * math.sin(deltaLat / 2) +
        math.cos(lat1) *
            math.cos(lat2) *
            math.sin(deltaLon / 2) *
            math.sin(deltaLon / 2);
    return earthRadiusMeters *
        2 *
        math.atan2(
          math.sqrt(haversine),
          math.sqrt(1 - haversine),
        );
  }

  static List<LatLng> squareAround(
    LatLng center, {
    double sideMeters = 12,
  }) {
    final halfSide = sideMeters / 2;
    final latDelta = halfSide / 111320;
    final lonDelta = halfSide /
        (111320 * math.cos(_radians(center.latitude)).abs().clamp(0.1, 1.0));

    return [
      LatLng(center.latitude + latDelta, center.longitude - lonDelta),
      LatLng(center.latitude + latDelta, center.longitude + lonDelta),
      LatLng(center.latitude - latDelta, center.longitude + lonDelta),
      LatLng(center.latitude - latDelta, center.longitude - lonDelta),
      LatLng(center.latitude + latDelta, center.longitude - lonDelta),
    ];
  }

  static double distanceToPolylineMeters(
    LatLng point,
    List<LatLng> polyline,
  ) {
    if (polyline.isEmpty) {
      return double.infinity;
    }
    if (polyline.length == 1) {
      return distanceMeters(point, polyline.single);
    }

    var shortestDistance = double.infinity;
    for (var index = 0; index < polyline.length - 1; index++) {
      shortestDistance = math.min(
        shortestDistance,
        _distanceToSegmentMeters(point, polyline[index], polyline[index + 1]),
      );
    }
    return shortestDistance;
  }

  static int nearestPointIndex(LatLng point, List<LatLng> polyline) {
    if (polyline.isEmpty) {
      return -1;
    }

    var nearestIndex = 0;
    var shortestDistance = double.infinity;
    for (var index = 0; index < polyline.length; index++) {
      final distance = distanceMeters(point, polyline[index]);
      if (distance < shortestDistance) {
        shortestDistance = distance;
        nearestIndex = index;
      }
    }
    return nearestIndex;
  }

  static double _distanceToSegmentMeters(
    LatLng point,
    LatLng start,
    LatLng end,
  ) {
    final referenceLatitude = _radians(point.latitude);
    final xScale = earthRadiusMeters * math.cos(referenceLatitude);
    const yScale = earthRadiusMeters;

    final pointX = _radians(point.longitude) * xScale;
    final pointY = _radians(point.latitude) * yScale;
    final startX = _radians(start.longitude) * xScale;
    final startY = _radians(start.latitude) * yScale;
    final endX = _radians(end.longitude) * xScale;
    final endY = _radians(end.latitude) * yScale;
    final segmentX = endX - startX;
    final segmentY = endY - startY;
    final segmentLengthSquared = segmentX * segmentX + segmentY * segmentY;

    if (segmentLengthSquared == 0) {
      return distanceMeters(point, start);
    }

    final projection =
        (((pointX - startX) * segmentX + (pointY - startY) * segmentY) /
                segmentLengthSquared)
            .clamp(0.0, 1.0);
    final closestX = startX + projection * segmentX;
    final closestY = startY + projection * segmentY;
    return math.sqrt(
      math.pow(pointX - closestX, 2) + math.pow(pointY - closestY, 2),
    );
  }

  static double _radians(double degrees) => degrees * math.pi / 180;
}
