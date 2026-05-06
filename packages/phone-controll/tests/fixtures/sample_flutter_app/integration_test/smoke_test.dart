// Patrol smoke test fixture — exercises the integration_test layer the
// Patrol orchestrator scans. Not executed unit-side; only used as a
// real-test target.
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:patrol/patrol.dart';

import 'package:sample_app/main.dart' as app;

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  patrolTest('shows greeting', ($) async {
    app.main();
    await $.pumpAndSettle();
    expect($('Hello, MCP'), findsOneWidget);
  });
}
