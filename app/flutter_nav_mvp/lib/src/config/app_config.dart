class AppConfig {
  const AppConfig._();

  static const valhallaBaseUrl = String.fromEnvironment(
    'VALHALLA_BASE_URL',
    defaultValue: 'http://localhost:8002',
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
