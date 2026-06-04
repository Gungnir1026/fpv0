import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_nav_mvp/src/services/polyline_codec.dart';

void main() {
  test('decodes Valhalla polyline6 coordinates', () {
    final points = PolylineCodec.decode('??AA');

    expect(points, hasLength(2));
    expect(points[0].latitude, 0);
    expect(points[0].longitude, 0);
    expect(points[1].latitude, closeTo(0.000001, 1e-12));
    expect(points[1].longitude, closeTo(0.000001, 1e-12));
  });

  test('rejects incomplete polyline coordinates', () {
    expect(() => PolylineCodec.decode('?'), throwsFormatException);
  });

  test('rejects invalid polyline characters', () {
    expect(() => PolylineCodec.decode(' ?'), throwsFormatException);
  });

  test('rejects negative precision', () {
    expect(
      () => PolylineCodec.decode('??', precision: -1),
      throwsArgumentError,
    );
  });
}
