import 'package:maplibre_gl/maplibre_gl.dart';

class PolylineCodec {
  const PolylineCodec._();

  static List<LatLng> decode(String encoded, {int precision = 6}) {
    if (precision < 0) {
      throw ArgumentError.value(precision, 'precision', 'must not be negative');
    }

    final coordinates = <LatLng>[];
    var index = 0;
    var latitude = 0;
    var longitude = 0;
    final factor = _pow10(precision);

    while (index < encoded.length) {
      final latResult = _decodeValue(encoded, index);
      index = latResult.nextIndex;
      latitude += latResult.delta;

      final lonResult = _decodeValue(encoded, index);
      index = lonResult.nextIndex;
      longitude += lonResult.delta;

      coordinates.add(LatLng(latitude / factor, longitude / factor));
    }

    return coordinates;
  }

  static double _pow10(int exponent) {
    var result = 1.0;
    for (var i = 0; i < exponent; i++) {
      result *= 10;
    }
    return result;
  }

  static _DecodedValue _decodeValue(String encoded, int startIndex) {
    if (startIndex >= encoded.length) {
      throw const FormatException('Polyline data is incomplete.');
    }

    var index = startIndex;
    var shift = 0;
    var result = 0;
    int byte;

    do {
      if (index >= encoded.length) {
        throw const FormatException('Polyline data is incomplete.');
      }
      byte = encoded.codeUnitAt(index++) - 63;
      if (byte < 0 || byte > 0x3f) {
        throw const FormatException('Polyline contains an invalid character.');
      }
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);

    final delta = (result & 1) != 0 ? ~(result >> 1) : result >> 1;
    return _DecodedValue(delta: delta, nextIndex: index);
  }
}

class _DecodedValue {
  const _DecodedValue({
    required this.delta,
    required this.nextIndex,
  });

  final int delta;
  final int nextIndex;
}
