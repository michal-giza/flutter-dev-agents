# `flutter-dev-agents/run-test-plan` GitHub Action

Run an autonomous mobile-test plan against an Android device or
emulator from any GitHub Actions workflow. Closes the gap between
"we have an MCP" and "your CI uses it."

## Quick usage

```yaml
# .github/workflows/mobile-smoke.yml in YOUR repo
name: mobile smoke
on: [push, pull_request]

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Boot Android emulator
        uses: ReactiveCircus/android-emulator-runner@v2
        with:
          api-level: 33
          script: |
            # Check out flutter-dev-agents into a sibling dir.
            git clone https://github.com/michal-giza/flutter-dev-agents.git \
              ../flutter-dev-agents
            # Run a plan against the booted emulator.
            cd ${{ github.workspace }}
      - uses: ./../flutter-dev-agents/.github/actions/run-test-plan
        with:
          plan: integration_test/plans/smoke.yaml
```

The action takes a YAML plan (file path OR inline), selects an
attached Android device (or the first booted emulator), invokes
`run_test_plan` via the MCP, releases the device, and fails the job
if the plan's verdict isn't `ok`.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `plan` | yes | — | Path to YAML plan file OR inline YAML starting with `apiVersion:` |
| `device-serial` | no | (auto-pick) | adb serial. Empty = first booted device |
| `project-path` | no | `.` | Path to the Flutter project |
| `python-version` | no | `3.11` | Python for the action's scratch venv |
| `extras` | no | `dev,ar,http` | pip extras (`ios` for iOS targets) |

## Outputs

| Output | Description |
|---|---|
| `envelope` | Full JSON envelope from `run_test_plan` — `{ok, data, error}` |
| `passed` | `"true"` if `ok=true`, else `"false"` |

## Example: report failure to Slack

```yaml
      - uses: ./../flutter-dev-agents/.github/actions/run-test-plan
        id: test
        with:
          plan: integration_test/plans/smoke.yaml
      - name: Notify on failure
        if: ${{ steps.test.outputs.passed == 'false' }}
        run: |
          curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
            -d "{\"text\":\"❌ Mobile smoke failed: ${{ steps.test.outputs.envelope }}\"}"
```

## Example: inline plan

```yaml
      - uses: ./../flutter-dev-agents/.github/actions/run-test-plan
        with:
          plan: |
            apiVersion: phone-controll/v1
            kind: TestPlan
            metadata: { name: smoke }
            spec:
              device: { platform: android, pool: any }
              project: { path: . }
              phases:
                - phase: PRE_FLIGHT
                - phase: CLEAN
                  package_id: com.example.app
                - phase: UNDER_TEST
                  driver: { kind: flutter_test, target: integration_test/smoke_test.dart }
                  capture: [screenshot, logs]
              report: { format: junit }
```

## Notes

- Runs entirely inside the consumer's runner — no remote MCP needed.
- The action installs `mcp-phone-controll` into a scratch venv per
  job, so it never pollutes the consumer's Python environment.
- Device lock is always released, even on plan failure (uses a
  `try/finally` in the dispatch chain).
- For iOS targets you need a macOS runner + Xcode + the `ios` extra.
  The same action covers it; just pass `extras: dev,ar,http,ios`.
