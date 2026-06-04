import 'package:flutter_test/flutter_test.dart';
import 'package:maplibre_gl/maplibre_gl.dart';
import 'package:flutter_nav_mvp/src/services/geo_math.dart';

void main() {
  test('computes short geographic distances in meters', () {
    final distance = GeoMath.distanceMeters(
      const LatLng(25.033, 121.543),
      const LatLng(25.033449, 121.543),
    );

    expect(distance, closeTo(50, 0.5));
  });

  test('creates a closed waiting-area square', () {
    final square = GeoMath.squareAround(
      const LatLng(25.033, 121.543),
      sideMeters: 12,
    );

    expect(square, hasLength(5));
    expect(square.first.latitude, square.last.latitude);
    expect(square.first.longitude, square.last.longitude);
  });

  test('computes distance from a point to a route segment', () {
    final distance = GeoMath.distanceToPolylineMeters(
      const LatLng(25.033449, 121.5435),
      const [
        LatLng(25.033, 121.543),
        LatLng(25.033, 121.544),
      ],
    );

    expect(distance, closeTo(50, 0.5));
  });

  test('finds the nearest route point index', () {
    final index = GeoMath.nearestPointIndex(
      const LatLng(25.033, 121.5439),
      const [
        LatLng(25.033, 121.543),
        LatLng(25.033, 121.544),
        LatLng(25.033, 121.545),
      ],
    );

    expect(index, 1);
  });
}
