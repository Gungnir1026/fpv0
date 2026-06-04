import 'dart:convert';

import 'package:flutter_nav_mvp/src/models/gps_sample.dart';
import 'package:flutter_nav_mvp/src/services/valhalla_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

void main() {
  test('posts motorcycle map matching request and parses route', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient((request) async {
        expect(request.url.path, '/trace_route');
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        expect(payload['costing'], 'motorcycle');
        expect(payload['shape_match'], 'map_snap');
        expect(payload['turn_lanes'], isTrue);
        expect(payload['shape'], hasLength(2));

        return http.Response(
          jsonEncode({
            'trip': {
              'summary': {'time': 12, 'length': 0.4},
              'legs': [
                {
                  'shape': '??AA',
                  'maneuvers': [
                    {
                      'type': 1,
                      'instruction': 'Continue',
                      'begin_shape_index': 0,
                      'end_shape_index': 1,
                      'length': 0.4,
                      'time': 12,
                    },
                  ],
                },
              ],
            },
          }),
          200,
        );
      }),
    );

    final trace = await client.traceRoute([_sample(), _sample()]);

    expect(trace.geometry, hasLength(2));
    expect(trace.lengthKm, 0.4);
    expect(trace.elapsedSeconds, 12);
    expect(trace.maneuvers, hasLength(1));
    client.close();
  });

  test('deduplicates a shared geometry point between legs', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient((_) async {
        return http.Response(
          jsonEncode({
            'trip': {
              'summary': {'time': 10, 'length': 0.1},
              'legs': [
                {'shape': '??AA'},
                {
                  'shape': 'AAAA',
                  'maneuvers': [
                    {
                      'type': 1,
                      'instruction': 'Continue',
                      'begin_shape_index': 0,
                      'end_shape_index': 1,
                      'length': 0.1,
                      'time': 10,
                    },
                  ],
                },
              ],
            },
          }),
          200,
        );
      }),
    );

    final trace = await client.traceRoute([_sample(), _sample()]);

    expect(trace.geometry, hasLength(3));
    expect(trace.maneuvers.single.beginShapeIndex, 1);
    client.close();
  });

  test('rejects invalid GPS coordinates before posting', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );

    expect(
      () => client.traceRoute([_sample(), _sample(latitude: 91)]),
      throwsA(isA<ValhallaException>()),
    );
    client.close();
  });

  test('includes Valhalla error detail for non-success response', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient(
        (_) async => http.Response('{"error":"bad shape"}', 400),
      ),
    );

    expect(
      () => client.traceRoute([_sample(), _sample()]),
      throwsA(
        isA<ValhallaException>().having(
          (error) => error.message,
          'message',
          contains('bad shape'),
        ),
      ),
    );
    client.close();
  });

  test('posts motorcycle route request and parses preview route', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient((request) async {
        expect(request.url.path, '/route');
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        expect(payload['costing'], 'motorcycle');
        expect(payload['turn_lanes'], isTrue);
        final locations = payload['locations'] as List<dynamic>;
        expect(locations, hasLength(2));
        expect(locations[0]['lat'], closeTo(25.0337, 1e-12));
        expect(locations[0]['lon'], closeTo(121.5434, 1e-12));
        expect(locations[1]['lat'], closeTo(25.0264, 1e-12));
        expect(locations[1]['lon'], closeTo(121.5348, 1e-12));

        return http.Response(
          jsonEncode({
            'trip': {
              'summary': {'time': 77, 'length': 0.32},
              'legs': [
                {'shape': '??AA'},
              ],
            },
          }),
          200,
        );
      }),
    );

    final route = await client.route(
      origin: const LatLng(25.0337, 121.5434),
      destination: const LatLng(25.0264, 121.5348),
    );

    expect(route.geometry, hasLength(2));
    expect(route.lengthKm, 0.32);
    expect(route.elapsedSeconds, 77);
    client.close();
  });

  test('rejects invalid destination before posting route request', () async {
    final client = ValhallaClient(
      baseUrl: 'http://localhost:8002',
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );

    expect(
      () => client.route(
        origin: const LatLng(25.0337, 121.5434),
        destination: const LatLng(91, 121.5348),
      ),
      throwsA(isA<ValhallaException>()),
    );
    client.close();
  });
}

GpsSample _sample({double latitude = 25.0337}) {
  return GpsSample(
    latitude: latitude,
    longitude: 121.5434,
    recordedAt: DateTime.fromMillisecondsSinceEpoch(0),
  );
}
