import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:maplibre_gl/maplibre_gl.dart';

import '../models/gps_sample.dart';
import '../models/navigation_maneuver.dart';
import '../models/navigation_route.dart';
import 'polyline_codec.dart';

class ValhallaClient {
  ValhallaClient({
    required String baseUrl,
    http.Client? httpClient,
    Duration requestTimeout = const Duration(seconds: 15),
  })  : _baseUri = Uri.parse(baseUrl),
        _httpClient = httpClient ?? http.Client(),
        _requestTimeout = requestTimeout;

  final Uri _baseUri;
  final http.Client _httpClient;
  final Duration _requestTimeout;

  Future<NavigationRoute> traceRoute(List<GpsSample> samples) async {
    if (samples.length < 2) {
      throw const ValhallaException('At least two GPS samples are required.');
    }
    if (samples.any((sample) => !sample.hasValidCoordinates)) {
      throw const ValhallaException('GPS samples contain invalid coordinates.');
    }

    return _postRoute(
      path: '/trace_route',
      operation: 'trace_route',
      payload: {
        'shape':
            samples.map((sample) => sample.toValhallaShapePoint()).toList(),
        'costing': 'motorcycle',
        'shape_match': 'map_snap',
        'directions_type': 'instructions',
        'turn_lanes': true,
        'units': 'kilometers',
      },
    );
  }

  Future<NavigationRoute> route({
    required LatLng origin,
    required LatLng destination,
  }) {
    _validateCoordinates(origin, label: 'Origin');
    _validateCoordinates(destination, label: 'Destination');

    return _postRoute(
      path: '/route',
      operation: 'route',
      payload: {
        'locations': [
          {'lat': origin.latitude, 'lon': origin.longitude},
          {'lat': destination.latitude, 'lon': destination.longitude},
        ],
        'costing': 'motorcycle',
        'directions_type': 'instructions',
        'turn_lanes': true,
        'units': 'kilometers',
      },
    );
  }

  Future<NavigationRoute> _postRoute({
    required String path,
    required String operation,
    required Map<String, Object?> payload,
  }) async {
    late final http.Response response;
    try {
      response = await _httpClient
          .post(
            _baseUri.resolve(path),
            headers: const {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(_requestTimeout);
    } on TimeoutException {
      throw ValhallaException('Navigation API $operation request timed out.');
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ValhallaException(
        'Navigation API $operation failed: HTTP ${response.statusCode}'
        '${_errorMessage(response.body)}',
      );
    }

    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ValhallaException('Unexpected Navigation API response.');
    }

    final trip = _jsonObject(decoded['trip']);
    if (trip == null) {
      throw const ValhallaException('Navigation API response missing trip.');
    }

    final decodedLegs = _decodeLegs(trip);
    final summary = _jsonObject(trip['summary']);

    return NavigationRoute(
      geometry: decodedLegs.geometry,
      elapsedSeconds: (summary?['time'] as num?)?.toDouble() ?? 0,
      lengthKm: (summary?['length'] as num?)?.toDouble() ?? 0,
      maneuvers: decodedLegs.maneuvers,
      rawJson: decoded,
    );
  }

  _DecodedLegs _decodeLegs(Map<String, dynamic> trip) {
    final legs = trip['legs'];
    if (legs is! List) {
      return const _DecodedLegs(geometry: [], maneuvers: []);
    }

    final points = <LatLng>[];
    final maneuvers = <NavigationManeuver>[];
    for (final rawLeg in legs) {
      final leg = _jsonObject(rawLeg);
      if (leg == null) {
        continue;
      }

      final shapeIndexOffset = _appendLegGeometry(points, leg['shape']);

      final rawManeuvers = leg['maneuvers'];
      if (rawManeuvers is List) {
        for (final rawManeuver in rawManeuvers) {
          if (rawManeuver is Map) {
            maneuvers.add(
              NavigationManeuver.fromJson(
                Map<String, dynamic>.from(rawManeuver),
                shapeIndexOffset: shapeIndexOffset,
              ),
            );
          }
        }
      }
    }
    return _DecodedLegs(geometry: points, maneuvers: maneuvers);
  }

  int _appendLegGeometry(List<LatLng> points, Object? rawShape) {
    if (rawShape is! String || rawShape.isEmpty) {
      return points.length;
    }

    final legPoints = PolylineCodec.decode(rawShape);
    if (points.isNotEmpty &&
        legPoints.isNotEmpty &&
        _sameCoordinate(points.last, legPoints.first)) {
      final shapeIndexOffset = points.length - 1;
      points.addAll(legPoints.skip(1));
      return shapeIndexOffset;
    }

    final shapeIndexOffset = points.length;
    points.addAll(legPoints);
    return shapeIndexOffset;
  }

  void close() {
    _httpClient.close();
  }
}

void _validateCoordinates(LatLng point, {required String label}) {
  if (!point.latitude.isFinite ||
      !point.longitude.isFinite ||
      point.latitude < -90 ||
      point.latitude > 90 ||
      point.longitude < -180 ||
      point.longitude > 180) {
    throw ValhallaException('$label contains invalid coordinates.');
  }
}

Map<String, dynamic>? _jsonObject(Object? value) {
  if (value is Map) {
    return Map<String, dynamic>.from(value);
  }
  return null;
}

bool _sameCoordinate(LatLng left, LatLng right) {
  return left.latitude == right.latitude && left.longitude == right.longitude;
}

String _errorMessage(String body) {
  if (body.isEmpty) {
    return '';
  }

  try {
    final decoded = jsonDecode(body);
    if (decoded is Map<String, dynamic>) {
      final message =
          decoded['error'] ?? decoded['status_message'] ?? decoded['status'];
      if (message != null) {
        return ': $message';
      }
    }
  } catch (_) {
    // Fall through to a short raw body excerpt.
  }

  final compact = body.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (compact.isEmpty) {
    return '';
  }
  return ': ${compact.length > 160 ? '${compact.substring(0, 160)}...' : compact}';
}

class _DecodedLegs {
  const _DecodedLegs({
    required this.geometry,
    required this.maneuvers,
  });

  final List<LatLng> geometry;
  final List<NavigationManeuver> maneuvers;
}

class ValhallaException implements Exception {
  const ValhallaException(this.message);

  final String message;

  @override
  String toString() => message;
}
