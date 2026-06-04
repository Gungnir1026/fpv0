import 'package:flutter_nav_mvp/src/models/navigation_route.dart';
import 'package:flutter_nav_mvp/src/models/navigation_session.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

void main() {
  const destination = LatLng(25.0264, 121.5348);
  const route = NavigationRoute(
    geometry: [
      LatLng(25.0337, 121.5434),
      destination,
    ],
    elapsedSeconds: 77,
    lengthKm: 0.32,
  );

  test('starts in regular map mode', () {
    const session = NavigationSession.map();

    expect(session.isMap, isTrue);
    expect(session.destination, isNull);
    expect(session.route, isNull);
  });

  test('preview cannot start navigation before route is available', () {
    const session = NavigationSession.preview(destination: destination);

    expect(session.isPreview, isTrue);
    expect(session.canStartNavigation, isFalse);
    expect(identical(session.startNavigation(), session), isTrue);
  });

  test('preview route transitions into active navigation', () {
    const preview = NavigationSession.preview(destination: destination);

    final navigating = preview.withRoute(route).startNavigation();

    expect(navigating.isNavigating, isTrue);
    expect(navigating.destination, destination);
    expect(navigating.route, route);
  });
}
