import 'package:geolocator/geolocator.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

class GpsSample {
  const GpsSample({
    required this.latitude,
    required this.longitude,
    required this.recordedAt,
    this.accuracyMeters,
    this.heading,
    this.speedMetersPerSecond,
  });

  factory GpsSample.fromPosition(Position position) {
    return GpsSample(
      latitude: position.latitude,
      longitude: position.longitude,
      recordedAt: position.timestamp,
      accuracyMeters: position.accuracy,
      heading: position.heading.isNaN ? null : position.heading,
      speedMetersPerSecond: position.speed.isNaN ? null : position.speed,
    );
  }

  final double latitude;
  final double longitude;
  final DateTime recordedAt;
  final double? accuracyMeters;
  final double? heading;
  final double? speedMetersPerSecond;

  LatLng get latLng => LatLng(latitude, longitude);

  bool get hasValidCoordinates =>
      latitude.isFinite &&
      longitude.isFinite &&
      latitude >= -90 &&
      latitude <= 90 &&
      longitude >= -180 &&
      longitude <= 180;

  double? get normalizedHeading {
    final value = heading;
    if (value == null || !value.isFinite || value < 0) {
      return null;
    }
    return value % 360;
  }

  double? get normalizedAccuracyMeters {
    final value = accuracyMeters;
    if (value == null || !value.isFinite || value < 0) {
      return null;
    }
    return value;
  }

  double? get normalizedSpeedMetersPerSecond {
    final value = speedMetersPerSecond;
    if (value == null || !value.isFinite || value < 0) {
      return null;
    }
    return value;
  }

  Map<String, Object?> toValhallaShapePoint() {
    final safeAccuracy = normalizedAccuracyMeters;
    final safeHeading = normalizedHeading;

    return {
      'lat': latitude,
      'lon': longitude,
      'time': recordedAt.millisecondsSinceEpoch ~/ 1000,
      if (safeAccuracy != null) 'accuracy': safeAccuracy,
      if (safeHeading != null) 'heading': safeHeading,
    };
  }
}
