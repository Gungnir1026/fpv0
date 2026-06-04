import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/navigation_maneuver.dart';

class LaneGuidancePanel extends StatelessWidget {
  const LaneGuidancePanel({
    required this.maneuver,
    super.key,
  });

  final NavigationManeuver maneuver;

  @override
  Widget build(BuildContext context) {
    if (maneuver.lanes.isEmpty) {
      return const SizedBox.shrink();
    }

    final scheme = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.outlineVariant),
        boxShadow: const [
          BoxShadow(
            color: Color(0x22000000),
            blurRadius: 16,
            offset: Offset(0, 6),
          ),
        ],
      ),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (maneuver.instruction.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    maneuver.instruction,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final lane in maneuver.lanes) _LaneTile(lane: lane),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LaneTile extends StatelessWidget {
  const _LaneTile({
    required this.lane,
  });

  final NavigationLane lane;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final direction = _primaryDirection(lane.directions);
    final activeColor = lane.isActive ? scheme.primary : scheme.secondary;
    final enabledColor = lane.isRecommended ? activeColor : scheme.outline;
    final foreground = lane.motorcycleAllowed ? enabledColor : scheme.outline;
    final background = lane.isRecommended
        ? enabledColor.withValues(alpha: lane.isActive ? 0.18 : 0.1)
        : scheme.surfaceContainerHighest.withValues(alpha: 0.72);

    return SizedBox(
      width: 48,
      height: 58,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: lane.isRecommended ? enabledColor : scheme.outlineVariant,
            width: lane.isActive ? 2 : 1,
          ),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            Transform.rotate(
              angle: _directionAngle(direction),
              child: Icon(
                Icons.arrow_upward,
                size: 28,
                color: foreground,
              ),
            ),
            if (!lane.motorcycleAllowed)
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: scheme.surface.withValues(alpha: 0.38),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.close,
                    size: 30,
                    color: scheme.error,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

LaneDirection _primaryDirection(List<LaneDirection> directions) {
  const priority = [
    LaneDirection.left,
    LaneDirection.right,
    LaneDirection.through,
    LaneDirection.slightLeft,
    LaneDirection.slightRight,
    LaneDirection.sharpLeft,
    LaneDirection.sharpRight,
    LaneDirection.reverse,
    LaneDirection.mergeToLeft,
    LaneDirection.mergeToRight,
    LaneDirection.none,
    LaneDirection.empty,
  ];

  for (final candidate in priority) {
    if (directions.contains(candidate)) {
      return candidate;
    }
  }
  return LaneDirection.empty;
}

double _directionAngle(LaneDirection direction) {
  return switch (direction) {
    LaneDirection.sharpLeft => -math.pi * 0.72,
    LaneDirection.left => -math.pi / 2,
    LaneDirection.slightLeft => -math.pi / 4,
    LaneDirection.through => 0,
    LaneDirection.slightRight => math.pi / 4,
    LaneDirection.right => math.pi / 2,
    LaneDirection.sharpRight => math.pi * 0.72,
    LaneDirection.reverse => math.pi,
    LaneDirection.mergeToLeft => -math.pi / 6,
    LaneDirection.mergeToRight => math.pi / 6,
    LaneDirection.none || LaneDirection.empty => 0,
  };
}
