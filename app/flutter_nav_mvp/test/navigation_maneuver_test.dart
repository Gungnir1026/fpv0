import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_nav_mvp/src/models/navigation_maneuver.dart';

void main() {
  test('parses lane guidance and motorcycle lane access', () {
    final maneuver = NavigationManeuver.fromJson(
      {
        'type': 15,
        'instruction': 'Turn left onto Xinyi Road.',
        'begin_shape_index': 2,
        'end_shape_index': 3,
        'length': 0.12,
        'time': 18,
        'motorcycle:lanes': 'no|yes|yes',
        'lanes': [
          {'directions': 8, 'active': 8},
          {'directions': 10, 'valid': 8},
          {'directions': 2},
        ],
      },
      shapeIndexOffset: 4,
    );

    expect(maneuver.beginShapeIndex, 6);
    expect(maneuver.lanes, hasLength(3));
    expect(maneuver.lanes[0].motorcycleAllowed, isFalse);
    expect(maneuver.lanes[0].isActive, isTrue);
    expect(maneuver.lanes[0].isRecommended, isFalse);
    expect(maneuver.lanes[1].isValid, isTrue);
    expect(maneuver.lanes[1].directions, contains(LaneDirection.left));
    expect(maneuver.lanes[2].directions, contains(LaneDirection.through));
  });

  test('detects custom two-stage turn restrictions', () {
    final maneuver = NavigationManeuver.fromJson(
      {
        'type': 15,
        'begin_shape_index': 0,
        'end_shape_index': 1,
        'custom': {
          'restriction:motorcycle': 'two_stage_turn',
        },
      },
      shapeIndexOffset: 0,
    );

    expect(maneuver.isTwoStageTurn, isTrue);
  });
}
