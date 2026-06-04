import 'package:maplibre_gl/maplibre_gl.dart';

import '../models/gps_sample.dart';
import '../models/navigation_maneuver.dart';
import '../models/navigation_route.dart';
import 'geo_math.dart';

class NavigationGuidance {
  const NavigationGuidance({
    this.matchedPositionMaxAge = const Duration(seconds: 5),
    this.matchedPositionMaxDistanceMeters = 25,
    this.twoStageTurnTriggerMeters = 50,
    this.laneGuidanceMaxDistanceMeters = 250,
  });

  final Duration matchedPositionMaxAge;
  final double matchedPositionMaxDistanceMeters;
  final double twoStageTurnTriggerMeters;
  final double laneGuidanceMaxDistanceMeters;

  LatLng navigationPosition({
    required GpsSample rawSample,
    NavigationRoute? matchedTrace,
    GpsSample? matchedThroughSample,
  }) {
    if (matchedTrace == null ||
        matchedTrace.geometry.isEmpty ||
        matchedThroughSample == null) {
      return rawSample.latLng;
    }

    final sampleAge =
        rawSample.recordedAt.difference(matchedThroughSample.recordedAt).abs();
    final sampleDistance = GeoMath.distanceMeters(
      rawSample.latLng,
      matchedThroughSample.latLng,
    );
    if (sampleAge <= matchedPositionMaxAge &&
        sampleDistance <= matchedPositionMaxDistanceMeters) {
      return matchedTrace.geometry.last;
    }
    return rawSample.latLng;
  }

  NavigationManeuver? nextManeuver({
    required NavigationRoute? route,
    required LatLng? position,
  }) {
    if (route == null || route.maneuvers.isEmpty || !route.hasGeometry) {
      return null;
    }
    if (position == null) {
      return route.maneuvers.first;
    }

    final nearestIndex = GeoMath.nearestPointIndex(position, route.geometry);
    for (final maneuver in route.maneuvers) {
      if (maneuver.beginShapeIndex >= nearestIndex) {
        return maneuver;
      }
    }
    return route.maneuvers.last;
  }

  NavigationManeuver? activeLaneGuidanceManeuver({
    required NavigationRoute? route,
    required LatLng? position,
  }) {
    if (route == null ||
        position == null ||
        route.maneuvers.isEmpty ||
        !route.hasGeometry) {
      return null;
    }

    final nearestIndex = GeoMath.nearestPointIndex(position, route.geometry);
    for (final maneuver in route.maneuvers) {
      if (!maneuver.hasLaneGuidance ||
          maneuver.beginShapeIndex < nearestIndex) {
        continue;
      }

      final point = maneuver.pointOn(route.geometry);
      if (point != null &&
          GeoMath.distanceMeters(position, point) <=
              laneGuidanceMaxDistanceMeters) {
        return maneuver;
      }
    }
    return null;
  }

  NavigationManeuver? nextTwoStageTurnWithinThreshold({
    required NavigationRoute? route,
    required LatLng? position,
  }) {
    if (route == null || position == null || !route.hasGeometry) {
      return null;
    }

    final nearestIndex = GeoMath.nearestPointIndex(position, route.geometry);
    for (final maneuver in route.maneuvers) {
      if (!maneuver.isTwoStageTurn || maneuver.beginShapeIndex < nearestIndex) {
        continue;
      }

      final point = maneuver.pointOn(route.geometry);
      if (point != null &&
          GeoMath.distanceMeters(position, point) <=
              twoStageTurnTriggerMeters) {
        return maneuver;
      }
    }
    return null;
  }
}
