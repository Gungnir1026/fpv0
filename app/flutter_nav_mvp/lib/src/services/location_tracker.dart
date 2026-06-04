import 'dart:async';

import 'package:geolocator/geolocator.dart';

import '../models/gps_sample.dart';

class LocationTracker {
  LocationTracker();

  Stream<GpsSample> get positionStream async* {
    await _ensureReady();

    const settings = LocationSettings(
      accuracy: LocationAccuracy.bestForNavigation,
      distanceFilter: 4,
    );

    yield* Geolocator.getPositionStream(
      locationSettings: settings,
    ).map(GpsSample.fromPosition);
  }

  Future<GpsSample> currentPosition() async {
    await _ensureReady();

    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.bestForNavigation,
      ),
    );
    return GpsSample.fromPosition(position);
  }

  Future<void> _ensureReady() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw const LocationTrackerException('Location service is disabled.');
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      throw const LocationTrackerException('Location permission denied.');
    }
    if (permission == LocationPermission.deniedForever) {
      throw const LocationTrackerException(
        'Location permission denied forever.',
      );
    }
  }
}

class LocationTrackerException implements Exception {
  const LocationTrackerException(this.message);

  final String message;

  @override
  String toString() => message;
}
