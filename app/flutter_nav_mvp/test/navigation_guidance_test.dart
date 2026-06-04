import 'package:flutter_nav_mvp/src/models/gps_sample.dart';
import 'package:flutter_nav_mvp/src/models/navigation_maneuver.dart';
import 'package:flutter_nav_mvp/src/models/navigation_route.dart';
import 'package:flutter_nav_mvp/src/services/navigation_guidance.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

void main() {
  const guidance = NavigationGuidance();
  final recordedAt = DateTime(2026, 5, 31);

  test('uses recent nearby snapped position for navigation guidance', () {
    final position = guidance.navigationPosition(
      rawSample: _sample(recordedAt: recordedAt),
      matchedTrace: _route(),
      matchedThroughSample: _sample(recordedAt: recordedAt),
    );

    expect(position, const LatLng(25.033, 121.544));
  });

  test('falls back to raw GPS when snapped position is too old', () {
    final rawSample = _sample(
      latitude: 25.034,
      recordedAt: recordedAt.add(const Duration(seconds: 6)),
    );

    final position = guidance.navigationPosition(
      rawSample: rawSample,
      matchedTrace: _route(),
      matchedThroughSample: _sample(recordedAt: recordedAt),
    );

    expect(position, rawSample.latLng);
  });

  test('falls back to raw GPS after a large location jump', () {
    final rawSample = _sample(latitude: 25.034, recordedAt: recordedAt);

    final position = guidance.navigationPosition(
      rawSample: rawSample,
      matchedTrace: _route(),
      matchedThroughSample: _sample(recordedAt: recordedAt),
    );

    expect(position, rawSample.latLng);
  });

  test('selects upcoming maneuver after passed shape points', () {
    final maneuver = guidance.nextManeuver(
      route: _route(),
      position: const LatLng(25.033, 121.5439),
    );

    expect(maneuver?.instruction, 'Second');
  });

  test('returns nearby upcoming lane guidance only', () {
    final maneuver = guidance.activeLaneGuidanceManeuver(
      route: _route(),
      position: const LatLng(25.033, 121.5439),
    );

    expect(maneuver?.instruction, 'Second');
  });

  test('returns nearby upcoming two-stage turn only', () {
    const shortRangeGuidance = NavigationGuidance(
      twoStageTurnTriggerMeters: 20,
    );

    expect(
      shortRangeGuidance.nextTwoStageTurnWithinThreshold(
        route: _route(),
        position: const LatLng(25.033, 121.5439),
      ),
      isNotNull,
    );
    expect(
      shortRangeGuidance.nextTwoStageTurnWithinThreshold(
        route: _route(),
        position: const LatLng(25.033, 121.543),
      ),
      isNull,
    );
  });
}

GpsSample _sample({
  double latitude = 25.033,
  double longitude = 121.543,
  required DateTime recordedAt,
}) {
  return GpsSample(
    latitude: latitude,
    longitude: longitude,
    recordedAt: recordedAt,
  );
}

NavigationRoute _route() {
  return const NavigationRoute(
    geometry: [
      LatLng(25.033, 121.543),
      LatLng(25.033, 121.5435),
      LatLng(25.033, 121.544),
    ],
    elapsedSeconds: 12,
    lengthKm: 0.1,
    maneuvers: [
      NavigationManeuver(
        type: 1,
        instruction: 'First',
        beginShapeIndex: 0,
        endShapeIndex: 1,
        lengthKm: 0.05,
        timeSeconds: 6,
        lanes: [],
        isTwoStageTurn: false,
      ),
      NavigationManeuver(
        type: 15,
        instruction: 'Second',
        beginShapeIndex: 2,
        endShapeIndex: 2,
        lengthKm: 0.05,
        timeSeconds: 6,
        lanes: [
          NavigationLane(
            directionsMask: 8,
            activeMask: 8,
          ),
        ],
        isTwoStageTurn: true,
      ),
    ],
  );
}
