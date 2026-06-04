import 'package:maplibre_gl/maplibre_gl.dart';

enum LaneDirection {
  empty(0),
  none(1),
  through(2),
  sharpLeft(4),
  left(8),
  slightLeft(16),
  slightRight(32),
  right(64),
  sharpRight(128),
  reverse(256),
  mergeToLeft(512),
  mergeToRight(1024);

  const LaneDirection(this.bit);

  final int bit;

  static List<LaneDirection> fromMask(int mask) {
    if (mask == 0) {
      return const [LaneDirection.empty];
    }

    return LaneDirection.values
        .where((direction) => direction != LaneDirection.empty)
        .where((direction) => mask & direction.bit != 0)
        .toList(growable: false);
  }
}

class NavigationLane {
  const NavigationLane({
    required this.directionsMask,
    this.validMask,
    this.activeMask,
    this.motorcycleAllowed = true,
  });

  factory NavigationLane.fromJson(
    Map<String, dynamic> json, {
    bool? motorcycleAllowed,
  }) {
    return NavigationLane(
      directionsMask: _intValue(json['directions']),
      validMask: _optionalIntValue(json['valid']),
      activeMask: _optionalIntValue(json['active']),
      motorcycleAllowed:
          motorcycleAllowed ?? _motorcycleAllowedFromLaneJson(json),
    );
  }

  final int directionsMask;
  final int? validMask;
  final int? activeMask;
  final bool motorcycleAllowed;

  bool get isActive => (activeMask ?? 0) != 0;
  bool get isValid => isActive || (validMask ?? 0) != 0;
  bool get isRecommended => motorcycleAllowed && isValid;

  List<LaneDirection> get directions =>
      LaneDirection.fromMask(preferredMask ?? directionsMask);

  int? get preferredMask {
    if ((activeMask ?? 0) != 0) {
      return activeMask;
    }
    if ((validMask ?? 0) != 0) {
      return validMask;
    }
    return null;
  }
}

class NavigationManeuver {
  const NavigationManeuver({
    required this.type,
    required this.instruction,
    required this.beginShapeIndex,
    required this.endShapeIndex,
    required this.lengthKm,
    required this.timeSeconds,
    required this.lanes,
    required this.isTwoStageTurn,
  });

  factory NavigationManeuver.fromJson(
    Map<String, dynamic> json, {
    required int shapeIndexOffset,
  }) {
    final motorcycleLaneAccess = _motorcycleLaneAccess(json);

    return NavigationManeuver(
      type: _intValue(json['type']),
      instruction: _stringValue(json['instruction']),
      beginShapeIndex: shapeIndexOffset + _intValue(json['begin_shape_index']),
      endShapeIndex: shapeIndexOffset + _intValue(json['end_shape_index']),
      lengthKm: _doubleValue(json['length']),
      timeSeconds: _doubleValue(json['time']),
      lanes: _lanesFromJson(json, motorcycleLaneAccess),
      isTwoStageTurn: _isTwoStageTurn(json),
    );
  }

  final int type;
  final String instruction;
  final int beginShapeIndex;
  final int endShapeIndex;
  final double lengthKm;
  final double timeSeconds;
  final List<NavigationLane> lanes;
  final bool isTwoStageTurn;

  bool get hasLaneGuidance => lanes.isNotEmpty;

  LatLng? pointOn(List<LatLng> geometry) {
    if (geometry.isEmpty) {
      return null;
    }

    final clampedIndex = beginShapeIndex.clamp(0, geometry.length - 1);
    return geometry[clampedIndex];
  }
}

int _intValue(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value) ?? 0;
  }
  return 0;
}

int? _optionalIntValue(Object? value) {
  if (value == null) {
    return null;
  }
  return _intValue(value);
}

double _doubleValue(Object? value) {
  if (value is num) {
    return value.toDouble();
  }
  if (value is String) {
    return double.tryParse(value) ?? 0;
  }
  return 0;
}

String _stringValue(Object? value) {
  if (value is String) {
    return value;
  }
  return '';
}

List<NavigationLane> _lanesFromJson(
  Map<String, dynamic> json,
  List<bool>? motorcycleLaneAccess,
) {
  final rawLanes = json['lanes'];
  if (rawLanes is List && rawLanes.isNotEmpty) {
    return [
      for (var i = 0; i < rawLanes.length; i++)
        if (rawLanes[i] is Map)
          NavigationLane.fromJson(
            Map<String, dynamic>.from(rawLanes[i] as Map),
            motorcycleAllowed:
                motorcycleLaneAccess != null && i < motorcycleLaneAccess.length
                    ? motorcycleLaneAccess[i]
                    : null,
          ),
    ];
  }

  if (motorcycleLaneAccess == null) {
    return const [];
  }

  return motorcycleLaneAccess
      .map(
        (allowed) => NavigationLane(
          directionsMask: LaneDirection.empty.bit,
          motorcycleAllowed: allowed,
        ),
      )
      .toList(growable: false);
}

List<bool>? _motorcycleLaneAccess(Map<String, dynamic> json) {
  final raw = _deepValue(json, const [
        'motorcycle:lanes',
      ]) ??
      _deepValue(json, const [
        'edge',
        'motorcycle:lanes',
      ]) ??
      _deepValue(json, const [
        'custom',
        'motorcycle:lanes',
      ]);

  if (raw is String && raw.trim().isNotEmpty) {
    return raw
        .split('|')
        .map((part) => !_isNoAccessValue(part))
        .toList(growable: false);
  }

  if (raw is List) {
    return raw.map((part) => !_isNoAccessValue(part)).toList(growable: false);
  }

  return null;
}

bool _motorcycleAllowedFromLaneJson(Map<String, dynamic> json) {
  final value = json['motorcycle_allowed'] ??
      json['motorcycleAllowed'] ??
      json['motorcycle'] ??
      json['motorcycle_access'] ??
      json['motorcycleAccess'] ??
      json['access'];

  return !_isNoAccessValue(value);
}

bool _isNoAccessValue(Object? value) {
  if (value is bool) {
    return !value;
  }
  final normalized = value?.toString().trim().toLowerCase();
  return normalized == 'no' ||
      normalized == 'false' ||
      normalized == '0' ||
      normalized == 'restricted';
}

bool _isTwoStageTurn(Map<String, dynamic> json) {
  final direct = json['restriction:motorcycle'] ??
      json['motorcycle_restriction'] ??
      json['motorcycleRestriction'] ??
      json['restriction_motorcycle'] ??
      json['maneuver_kind'] ??
      json['kind'];
  final nested = _deepValue(json, const [
        'custom',
        'restriction:motorcycle',
      ]) ??
      _deepValue(json, const [
        'edge',
        'restriction:motorcycle',
      ]);

  return _isTwoStageTurnValue(direct) || _isTwoStageTurnValue(nested);
}

bool _isTwoStageTurnValue(Object? value) {
  final normalized = value?.toString().trim().toLowerCase();
  return normalized == 'two_stage_turn' ||
      normalized == 'two-stage-turn' ||
      normalized == 'two stage turn';
}

Object? _deepValue(Map<String, dynamic> json, List<String> path) {
  Object? current = json;
  for (final key in path) {
    if (current is! Map) {
      return null;
    }
    current = current[key];
  }
  return current;
}
