import 'package:flutter/material.dart';

import '../models/navigation_maneuver.dart';
import '../models/navigation_route.dart';

class NavigationStatusBar extends StatelessWidget {
  const NavigationStatusBar({
    super.key,
    required this.status,
    required this.tracking,
    required this.busy,
    required this.route,
  });

  final String status;
  final bool tracking;
  final bool busy;
  final NavigationRoute? route;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: _panelDecoration(scheme),
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 48, maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                tracking ? Icons.navigation : Icons.pause_circle,
                color: tracking ? scheme.primary : scheme.outline,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  status,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              const SizedBox(width: 12),
              _StatusDot(
                active: busy,
                activeColor: const Color(0xff0077b6),
              ),
              const SizedBox(width: 8),
              Text(
                route == null
                    ? '--'
                    : '${route!.elapsedSeconds.toStringAsFixed(0)} s',
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class NextManeuverPanel extends StatelessWidget {
  const NextManeuverPanel({
    super.key,
    required this.maneuver,
  });

  final NavigationManeuver maneuver;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: _panelDecoration(scheme),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.turn_right, color: scheme.primary),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  maneuver.instruction,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class RoutePreviewPanel extends StatelessWidget {
  const RoutePreviewPanel({
    super.key,
    required this.route,
    required this.routing,
    required this.onStart,
    required this.onCancel,
  });

  final NavigationRoute? route;
  final bool routing;
  final VoidCallback onStart;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return _RoutePanel(
      icon: Icons.route,
      title: routing ? '規劃路線' : '路線預覽',
      route: route,
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            tooltip: '取消',
            onPressed: onCancel,
            icon: const Icon(Icons.close),
          ),
          FilledButton.icon(
            onPressed: route?.hasGeometry == true && !routing ? onStart : null,
            icon: const Icon(Icons.navigation),
            label: const Text('開始'),
          ),
        ],
      ),
    );
  }
}

class ActiveNavigationPanel extends StatelessWidget {
  const ActiveNavigationPanel({
    super.key,
    required this.route,
    required this.rerouting,
    required this.onEnd,
  });

  final NavigationRoute? route;
  final bool rerouting;
  final VoidCallback onEnd;

  @override
  Widget build(BuildContext context) {
    return _RoutePanel(
      icon: Icons.navigation,
      title: rerouting ? '重新規劃' : '導航中',
      route: route,
      trailing: IconButton(
        tooltip: '結束導航',
        onPressed: onEnd,
        icon: const Icon(Icons.close),
      ),
    );
  }
}

class MapControls extends StatelessWidget {
  const MapControls({
    super.key,
    required this.tracking,
    required this.onCenter,
    required this.onToggleTracking,
    required this.onCancelRoute,
  });

  final bool tracking;
  final VoidCallback onCenter;
  final VoidCallback onToggleTracking;
  final VoidCallback? onCancelRoute;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: _panelDecoration(scheme),
      child: SizedBox(
        height: 56,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _IconAction(
              icon: Icons.my_location,
              tooltip: '置中',
              onPressed: onCenter,
            ),
            _IconAction(
              icon: tracking ? Icons.pause : Icons.play_arrow,
              tooltip: tracking ? '暫停定位' : '開始定位',
              onPressed: onToggleTracking,
            ),
            if (onCancelRoute != null)
              _IconAction(
                icon: Icons.close,
                tooltip: '取消路線',
                onPressed: onCancelRoute!,
              ),
          ],
        ),
      ),
    );
  }
}

class _RoutePanel extends StatelessWidget {
  const _RoutePanel({
    required this.icon,
    required this.title,
    required this.route,
    required this.trailing,
  });

  final IconData icon;
  final String title;
  final NavigationRoute? route;
  final Widget trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: _panelDecoration(scheme),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          children: [
            Icon(icon, color: scheme.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleSmall),
                  Text(
                    route == null
                        ? '等待路線'
                        : '${route!.lengthKm.toStringAsFixed(2)} km · ${_durationLabel(route!.elapsedSeconds)}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            trailing,
          ],
        ),
      ),
    );
  }
}

class _StatusDot extends StatelessWidget {
  const _StatusDot({
    required this.active,
    required this.activeColor,
  });

  final bool active;
  final Color activeColor;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 160),
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color:
            active ? activeColor : Theme.of(context).colorScheme.outlineVariant,
        shape: BoxShape.circle,
      ),
    );
  }
}

class _IconAction extends StatelessWidget {
  const _IconAction({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: 54,
      child: IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        icon: Icon(icon),
      ),
    );
  }
}

BoxDecoration _panelDecoration(ColorScheme scheme) {
  return BoxDecoration(
    color: scheme.surface.withValues(alpha: 0.94),
    borderRadius: BorderRadius.circular(8),
    border: Border.all(color: scheme.outlineVariant),
    boxShadow: const [
      BoxShadow(
        color: Color(0x22000000),
        blurRadius: 16,
        offset: Offset(0, 6),
      ),
    ],
  );
}

String _durationLabel(double seconds) {
  final minutes = (seconds / 60).ceil();
  return '$minutes 分鐘';
}
