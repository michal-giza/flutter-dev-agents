# sample_flutter_app — opt-in MCP fixture

Minimal Flutter project used by `tests/integration_real/`. Not exercised by
the default `pytest` run. To use it:

    cd tests/fixtures/sample_flutter_app && flutter pub get
    MCP_REAL=1 pytest tests/integration_real

The `lib/main.dart` renders a single screen. The `integration_test/`
directory exists so `list_patrol_tests` and `run_patrol_test` have
something concrete to scan and run when you wire a device.

This is a **fixture**, not a Flutter app worth running. Treat it like
golden test data: it changes when the MCP's project-shape expectations
change, never to match your current Flutter SDK version.
