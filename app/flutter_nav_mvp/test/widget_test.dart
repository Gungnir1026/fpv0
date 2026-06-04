import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_nav_mvp/src/navigation_app.dart';

void main() {
  test('creates the navigation app shell', () {
    const app = NavigationApp();

    expect(app, isA<NavigationApp>());
  });
}
