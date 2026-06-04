import 'package:maplibre_gl/maplibre_gl.dart';

import 'navigation_route.dart';

enum NavigationSessionMode {
  map,
  preview,
  navigating,
}

class NavigationSession {
  const NavigationSession._({
    required this.mode,
    this.destination,
    this.route,
  });

  const NavigationSession.map() : this._(mode: NavigationSessionMode.map);

  const NavigationSession.preview({
    required LatLng destination,
    NavigationRoute? route,
  }) : this._(
          mode: NavigationSessionMode.preview,
          destination: destination,
          route: route,
        );

  final NavigationSessionMode mode;
  final LatLng? destination;
  final NavigationRoute? route;

  bool get isMap => mode == NavigationSessionMode.map;
  bool get isPreview => mode == NavigationSessionMode.preview;
  bool get isNavigating => mode == NavigationSessionMode.navigating;
  bool get canStartNavigation => isPreview && route?.hasGeometry == true;

  NavigationSession withRoute(NavigationRoute route) {
    final selectedDestination = destination;
    if (selectedDestination == null) {
      return this;
    }

    return NavigationSession._(
      mode: mode,
      destination: selectedDestination,
      route: route,
    );
  }

  NavigationSession startNavigation() {
    if (!canStartNavigation) {
      return this;
    }

    return NavigationSession._(
      mode: NavigationSessionMode.navigating,
      destination: destination,
      route: route,
    );
  }
}
