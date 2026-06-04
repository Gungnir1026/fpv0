import 'package:flutter/material.dart';

import 'widgets/navigation_map_page.dart';

class NavigationApp extends StatelessWidget {
  const NavigationApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'TW Moto Nav',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff005f73),
          brightness: Brightness.light,
        ),
        visualDensity: VisualDensity.standard,
      ),
      home: const NavigationMapPage(),
    );
  }
}
