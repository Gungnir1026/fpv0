import 'package:maplibre_gl/maplibre_gl.dart';

import 'navigation_maneuver.dart';

class NavigationRoute {
  const NavigationRoute({
    required this.geometry,
    required this.elapsedSeconds,
    required this.lengthKm,
    this.maneuvers = const [],
    this.rawJson,
  });

  final List<LatLng> geometry;
  final double elapsedSeconds;
  final double lengthKm;
  final List<NavigationManeuver> maneuvers;
  final Map<String, dynamic>? rawJson;

  bool get hasGeometry => geometry.length >= 2;

  NavigationManeuver? get firstLaneGuidanceManeuver {
    for (final maneuver in maneuvers) {
      if (maneuver.hasLaneGuidance) {
        return maneuver;
      }
    }
    return null;
  }
}
