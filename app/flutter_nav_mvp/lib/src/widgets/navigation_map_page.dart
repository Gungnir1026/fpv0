import 'dart:async';

import 'package:flutter/material.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

import '../config/app_config.dart';
import '../models/gps_sample.dart';
import '../models/navigation_route.dart';
import '../models/navigation_session.dart';
import '../services/geo_math.dart';
import '../services/location_tracker.dart';
import '../services/valhalla_client.dart';
import '../services/navigation_guidance.dart';
import 'lane_guidance_panel.dart';
import 'navigation_map_overlays.dart';
import 'navigation_panels.dart';

class NavigationMapPage extends StatefulWidget {
  const NavigationMapPage({super.key});

  @override
  State<NavigationMapPage> createState() => _NavigationMapPageState();
}

class _NavigationMapPageState extends State<NavigationMapPage> {
  static const _daanCenter = LatLng(25.033, 121.543);
  static const _traceResetDistanceMeters = 1000.0;

  final _locationTracker = LocationTracker();
  final _guidance = const NavigationGuidance();
  final _mapOverlays = NavigationMapOverlays();
  late final ValhallaClient _valhallaClient;

  StreamSubscription<GpsSample>? _locationSubscription;
  final List<GpsSample> _recentSamples = [];
  Future<void> _gpsSampleQueue = Future<void>.value();
  Future<void> _annotationQueue = Future<void>.value();

  NavigationSession _session = const NavigationSession.map();
  bool _tracking = false;
  bool _matching = false;
  bool _routing = false;
  String _status = '等待定位';
  GpsSample? _latestRawSample;
  NavigationRoute? _latestMatchedTrace;
  GpsSample? _latestMatchedThroughSample;
  DateTime _lastMatchAt = DateTime.fromMillisecondsSinceEpoch(0);
  DateTime _lastRouteCalculationAt = DateTime.fromMillisecondsSinceEpoch(0);
  int _traceRevision = 0;
  int _routeRevision = 0;

  @override
  void initState() {
    super.initState();
    _valhallaClient = ValhallaClient(baseUrl: AppConfig.valhallaBaseUrl);
    WidgetsBinding.instance.addPostFrameCallback((_) => _startTracking());
  }

  @override
  void dispose() {
    _locationSubscription?.cancel();
    _valhallaClient.close();
    _mapOverlays.clearController();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final route = _session.route;
    final position = _currentNavigationPosition();
    final nextManeuver = _session.isNavigating
        ? _guidance.nextManeuver(route: route, position: position)
        : null;
    final laneGuidanceManeuver = _session.isNavigating
        ? _guidance.activeLaneGuidanceManeuver(
            route: route,
            position: position,
          )
        : null;

    return Scaffold(
      body: Stack(
        children: [
          MapLibreMap(
            styleString: AppConfig.mapStyleUrl,
            initialCameraPosition: const CameraPosition(
              target: _daanCenter,
              zoom: 14,
            ),
            myLocationEnabled: true,
            myLocationTrackingMode: MyLocationTrackingMode.none,
            compassEnabled: true,
            trackCameraPosition: true,
            onMapCreated: _onMapCreated,
            onStyleLoadedCallback: _onStyleLoaded,
            onMapLongClick: (_, coordinates) {
              unawaited(_selectDestination(coordinates));
            },
          ),
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    NavigationStatusBar(
                      status: _status,
                      tracking: _tracking,
                      busy: _routing || _matching,
                      route: route,
                    ),
                    if (nextManeuver != null) ...[
                      const SizedBox(height: 8),
                      NextManeuverPanel(maneuver: nextManeuver),
                    ],
                    if (laneGuidanceManeuver != null) ...[
                      const SizedBox(height: 8),
                      LaneGuidancePanel(maneuver: laneGuidanceManeuver),
                    ],
                  ],
                ),
              ),
            ),
          ),
          SafeArea(
            child: Align(
              alignment: Alignment.bottomCenter,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_session.isPreview)
                      RoutePreviewPanel(
                        route: route,
                        routing: _routing,
                        onStart: _startNavigation,
                        onCancel: _clearNavigationSession,
                      ),
                    if (_session.isNavigating)
                      ActiveNavigationPanel(
                        route: route,
                        rerouting: _routing,
                        onEnd: _clearNavigationSession,
                      ),
                    if (!_session.isMap) const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.bottomRight,
                      child: MapControls(
                        tracking: _tracking,
                        onCenter: _centerOnLatestPosition,
                        onToggleTracking:
                            _tracking ? _stopTracking : _startTracking,
                        onCancelRoute:
                            _session.isMap ? null : _clearNavigationSession,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _onMapCreated(MapLibreMapController controller) {
    _mapOverlays.setController(controller);
  }

  Future<void> _onStyleLoaded() async {
    await _queueAnnotationUpdate(() async {
      await _mapOverlays.resetAfterStyleLoaded(
        rawSample: _latestRawSample,
        destination: _session.destination,
        route: _session.route,
        navigating: _session.isNavigating,
        twoStageTurnPoint: _nextTwoStageTurnPoint(),
      );
    });
  }

  Future<void> _startTracking() async {
    if (_tracking) {
      return;
    }

    setState(() {
      _status = '啟動 GPS';
      _tracking = true;
    });

    try {
      final current = await _locationTracker.currentPosition();
      if (!mounted) {
        return;
      }
      await _handleGpsSample(current);
      if (!mounted) {
        return;
      }

      await _locationSubscription?.cancel();
      _locationSubscription = _locationTracker.positionStream.listen(
        _queueGpsSample,
        onError: _handleTrackingError,
      );
    } catch (error) {
      _handleTrackingError(error);
    }
  }

  void _queueGpsSample(GpsSample sample) {
    _gpsSampleQueue = _gpsSampleQueue
        .then((_) => _handleGpsSample(sample))
        .catchError((Object error, StackTrace stackTrace) {
      _handleTrackingError(error);
    });
  }

  void _handleTrackingError(Object error) {
    if (!mounted) {
      return;
    }
    setState(() {
      _status = error.toString();
      _tracking = false;
    });
  }

  Future<void> _stopTracking() async {
    await _locationSubscription?.cancel();
    _locationSubscription = null;
    if (!mounted) {
      return;
    }
    setState(() {
      _tracking = false;
      _status = '定位已暫停';
    });
  }

  Future<void> _handleGpsSample(GpsSample sample) async {
    if (!sample.hasValidCoordinates) {
      if (mounted) {
        setState(() {
          _status = 'GPS 座標無效';
        });
      }
      return;
    }

    final previousSample = _latestRawSample;
    if (previousSample != null &&
        GeoMath.distanceMeters(previousSample.latLng, sample.latLng) >
            _traceResetDistanceMeters) {
      _resetMatchedTrace();
    }

    _latestRawSample = sample;
    _recentSamples.add(sample);
    if (_recentSamples.length > AppConfig.maxTraceSamples) {
      _recentSamples.removeRange(
        0,
        _recentSamples.length - AppConfig.maxTraceSamples,
      );
    }

    if (!mounted) {
      return;
    }
    setState(() {
      if (_session.isMap) {
        _status =
            'GPS ${sample.normalizedAccuracyMeters?.toStringAsFixed(0) ?? '-'} m';
      }
    });

    await _queueAnnotationUpdate(() async {
      await _mapOverlays.drawRawGps(sample);
      await _updateTwoStageTurnOverlay();
    });

    if (_session.isPreview && _session.route == null && !_routing) {
      unawaited(_planRoute());
    }
    if (!_session.isNavigating) {
      return;
    }

    _rerouteWhenNeeded(sample);
    final now = DateTime.now();
    if (now.difference(_lastMatchAt) >= AppConfig.mapMatchingInterval) {
      unawaited(_matchCurrentTrace());
    }
  }

  Future<void> _selectDestination(LatLng destination) async {
    _routeRevision++;
    setState(() {
      _session = NavigationSession.preview(destination: destination);
      _routing = false;
      _status = _latestRawSample == null ? '等待 GPS 後規劃路線' : '規劃路線';
    });

    await _queueAnnotationUpdate(() async {
      await _mapOverlays.clearPlannedRoute();
      await _mapOverlays.removeTwoStageTurn();
      await _mapOverlays.drawDestination(destination);
    });
    if (_latestRawSample != null) {
      await _planRoute();
    }
  }

  Future<void> _planRoute({bool isReroute = false}) async {
    final destination = _session.destination;
    final origin = _latestRawSample?.latLng;
    if (_routing || destination == null || origin == null) {
      return;
    }

    final requestRevision = ++_routeRevision;
    _lastRouteCalculationAt = DateTime.now();
    setState(() {
      _routing = true;
      _status = isReroute ? '偏離路線，重新規劃' : '規劃路線';
    });

    try {
      final route = await _valhallaClient.route(
        origin: origin,
        destination: destination,
      );
      if (requestRevision != _routeRevision) {
        return;
      }
      if (!route.hasGeometry) {
        throw const ValhallaException(
          'Valhalla route response missing geometry.',
        );
      }

      _session = _session.withRoute(route);
      await _queueAnnotationUpdate(() async {
        await _mapOverlays.drawPlannedRoute(
          _session.route,
          navigating: _session.isNavigating,
        );
        await _updateTwoStageTurnOverlay();
      });
      if (!mounted) {
        return;
      }
      setState(() {
        _status = _session.isNavigating ? '導航中' : '路線預覽';
      });
    } catch (error) {
      if (!mounted || requestRevision != _routeRevision) {
        return;
      }
      setState(() {
        _status = error.toString();
      });
    } finally {
      if (mounted && requestRevision == _routeRevision) {
        setState(() {
          _routing = false;
        });
      }
    }
  }

  void _startNavigation() {
    final nextSession = _session.startNavigation();
    if (identical(nextSession, _session)) {
      return;
    }

    _resetMatchedTrace(keepLatestSample: true);
    setState(() {
      _session = nextSession;
      _status = '導航中';
    });
    unawaited(
      _queueAnnotationUpdate(() async {
        await _mapOverlays.drawPlannedRoute(
          _session.route,
          navigating: _session.isNavigating,
        );
        await _updateTwoStageTurnOverlay();
      }),
    );
  }

  Future<void> _clearNavigationSession() async {
    _routeRevision++;
    _resetMatchedTrace();
    setState(() {
      _session = const NavigationSession.map();
      _routing = false;
      _status = '一般地圖';
    });
    await _queueAnnotationUpdate(() async {
      await _mapOverlays.clearPlannedRoute();
      await _mapOverlays.removeDestination();
      await _mapOverlays.removeTwoStageTurn();
    });
  }

  void _resetMatchedTrace({bool keepLatestSample = false}) {
    final latestSample = _latestRawSample;
    _traceRevision++;
    _latestMatchedTrace = null;
    _latestMatchedThroughSample = null;
    _recentSamples.clear();
    if (keepLatestSample && latestSample != null) {
      _recentSamples.add(latestSample);
    }
  }

  Future<void> _queueAnnotationUpdate(
    Future<void> Function() update,
  ) {
    _annotationQueue = _annotationQueue.then((_) => update()).catchError(
      (Object error, StackTrace stackTrace) {
        if (!mounted) {
          return;
        }
        setState(() {
          _status = '地圖更新失敗：$error';
        });
      },
    );
    return _annotationQueue;
  }

  void _rerouteWhenNeeded(GpsSample sample) {
    final route = _session.route;
    if (_routing || route == null || !route.hasGeometry) {
      return;
    }

    final now = DateTime.now();
    if (now.difference(_lastRouteCalculationAt) <
        AppConfig.routeRecalculationInterval) {
      return;
    }

    final distance = GeoMath.distanceToPolylineMeters(
      _guidance.navigationPosition(
        rawSample: sample,
        matchedTrace: _latestMatchedTrace,
        matchedThroughSample: _latestMatchedThroughSample,
      ),
      route.geometry,
    );
    if (distance > AppConfig.routeDeviationThresholdMeters) {
      unawaited(_planRoute(isReroute: true));
    }
  }

  Future<void> _matchCurrentTrace() async {
    if (!_session.isNavigating || _matching || _recentSamples.length < 2) {
      return;
    }

    _matching = true;
    _lastMatchAt = DateTime.now();
    final traceRevision = _traceRevision;
    if (!mounted) {
      _matching = false;
      return;
    }
    setState(() {});

    final samples = List<GpsSample>.unmodifiable(_recentSamples);
    try {
      final matchedTrace = await _valhallaClient.traceRoute(samples);
      if (traceRevision != _traceRevision || !_session.isNavigating) {
        return;
      }
      _latestMatchedTrace = matchedTrace;
      _latestMatchedThroughSample = samples.last;
    } catch (error) {
      if (!mounted ||
          traceRevision != _traceRevision ||
          !_session.isNavigating) {
        return;
      }
      setState(() {
        _status = error.toString();
      });
    } finally {
      _matching = false;
      if (mounted) {
        setState(() {});
      }
    }
  }

  Future<void> _updateTwoStageTurnOverlay() async {
    await _mapOverlays.updateTwoStageTurn(_nextTwoStageTurnPoint());
  }

  LatLng? _nextTwoStageTurnPoint() {
    if (!_session.isNavigating) {
      return null;
    }
    final maneuver = _guidance.nextTwoStageTurnWithinThreshold(
      route: _session.route,
      position: _currentNavigationPosition(),
    );
    return maneuver?.pointOn(_session.route?.geometry ?? const []);
  }

  LatLng? _currentNavigationPosition() {
    final sample = _latestRawSample;
    if (sample == null) {
      return null;
    }
    return _guidance.navigationPosition(
      rawSample: sample,
      matchedTrace: _latestMatchedTrace,
      matchedThroughSample: _latestMatchedThroughSample,
    );
  }

  Future<void> _centerOnLatestPosition() async {
    await _mapOverlays.centerOnLatestPosition();
  }
}
