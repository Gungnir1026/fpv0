class AppConfig {
  const AppConfig._();

  static const _legacyNavigationApiBaseUrl = String.fromEnvironment(
    'VALHALLA_BASE_URL',
    defaultValue: 'http://localhost:8010',
  );

  static const navigationApiBaseUrl = String.fromEnvironment(
    'NAVIGATION_API_BASE_URL',
    defaultValue: _legacyNavigationApiBaseUrl,
  );

  static const mapStyleUrl = String.fromEnvironment(
    'MAP_STYLE_URL',
    defaultValue: 'https://tiles.openfreemap.org/styles/liberty',
  );

  static const mapMatchingInterval = Duration(seconds: 3);
  static const routeRecalculationInterval = Duration(seconds: 12);
  static const routeDeviationThresholdMeters = 55.0;
  static const maxTraceSamples = 24;
}
