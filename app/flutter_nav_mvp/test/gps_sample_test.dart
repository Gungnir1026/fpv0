import 'package:flutter_nav_mvp/src/models/gps_sample.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ignores unavailable simulator heading', () {
    final sample = _sample(heading: -1);

    expect(sample.normalizedHeading, isNull);
    expect(sample.toValhallaShapePoint(), isNot(contains('heading')));
  });

  test('normalizes heading before sending it to native map code', () {
    final sample = _sample(heading: 725);

    expect(sample.normalizedHeading, 5);
    expect(sample.toValhallaShapePoint()['heading'], 5);
  });

  test('rejects invalid GPS coordinates', () {
    final sample = _sample(latitude: 91);

    expect(sample.hasValidCoordinates, isFalse);
  });

  test('omits invalid optional sensor values from Valhalla payload', () {
    final sample = _sample(
      accuracyMeters: double.infinity,
      speedMetersPerSecond: -1,
    );

    expect(sample.normalizedAccuracyMeters, isNull);
    expect(sample.normalizedSpeedMetersPerSecond, isNull);
    expect(sample.toValhallaShapePoint(), isNot(contains('accuracy')));
  });
}

GpsSample _sample({
  double latitude = 25.0337,
  double longitude = 121.5434,
  double? heading,
  double? accuracyMeters,
  double? speedMetersPerSecond,
}) {
  return GpsSample(
    latitude: latitude,
    longitude: longitude,
    recordedAt: DateTime.fromMillisecondsSinceEpoch(0),
    heading: heading,
    accuracyMeters: accuracyMeters,
    speedMetersPerSecond: speedMetersPerSecond,
  );
}
