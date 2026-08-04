# Patrol 4 factory enablement — what each app needs

How to make any Flutter app in the factory end-to-end testable with the
**newest Patrol** (patrol **4.8.0** / patrol_cli **4.6.1**), on **mobile and
web**, and drivable by phone-controll. Plus the one-time **physical iPhone**
runbook for iOS UI driving.

> **Confidence note.** The pubspec, native-harness, CLI, CI, and device
> sections below are verified against the toolchain on this machine
> (patrol_cli **4.6.1**, patrol **4.8.0**, Xcode **26.6**) — every generated
> CLI flag was executed, not guessed. The Patrol **Dart API** used by
> `scaffold_patrol_test` is compile-verified with a real `flutter analyze`
> against a resolved patrol 4.7.1+; if you hand-write beyond that surface,
> confirm with one throwaway test before templating it across the factory.

---

## 0. Version compatibility (read this first)

Compatibility is a **floor, not a strict pairing** — an earlier version of
this doc overstated it as lockstep, which is wrong and has been corrected.

- **Any patrol_cli ≥ 4.5.0 works with any patrol ≥ 4.7.0.** A CLI-only bump
  is legal; you do not have to move both in lockstep.
- **patrol ≥ 4.8.0** is what unlocks the newer `--web-*` options — the
  runner-side wiring landed in 4.8.0, so the CLI flag alone isn't enough.
- Installed here: **patrol_cli 4.6.1**, newest patrol **4.8.0**.
- Moving to the 4.x line **is** a breaking change for an app still on
  patrol 3.x. Bump the app and migrate its native-automation calls in the
  same PR, or that app's Patrol runs fail the version gate.
- Roll back if an app can't migrate yet: `dart pub global activate patrol_cli 3.11.0`.

**`--web-headless` changed shape in patrol_cli 4.6.0** — from a value option
(`--web-headless=<true|false>`) to a negatable boolean (`--[no-]web-headless`).
The value form still parses on 4.6.x but warns and is slated for removal.
phone-controll emits whichever form your **installed** CLI accepts, so both
4.5.x and 4.6.x users are safe; you don't need to do anything.

phone-controll's web path **fails closed** below patrol_cli 4.0.0 with
`next_action="upgrade_patrol_cli"` — it won't emit web flags an old CLI
would reject.

---

## 1. Per-app checklist — MOBILE (Android + iOS)

**pubspec.yaml**

```yaml
environment:
  sdk: ">=3.8.0 <4.0.0"      # Patrol 4 requires Dart >= 3.8
  flutter: ">=3.32.0"        # and Flutter >= 3.32

dev_dependencies:
  patrol: ^4.7.0             # floor; caret resolves to 4.8.0 on a fresh pub get
  integration_test:
    sdk: flutter
  flutter_test:
    sdk: flutter
# do NOT list patrol_finders — patrol bundles it

# top-level (NOT under flutter:) — templated per app
patrol:
  app_name: My App
  android:
    package_name: com.factory.myapp   # == applicationId
  ios:
    bundle_id: com.factory.myapp       # == PRODUCT_BUNDLE_IDENTIFIER
```

**Test layout** — Patrol 4 defaults to **`patrol_test/`** (moved from
`integration_test/` in 4.0.0). phone-controll's `list_patrol_tests` scans
both, but new apps should use `patrol_test/`. Key assertions on **widget
`Key`s, never localized text** — the locale-independence lesson this whole
toolchain was built around (a Polish-locale phone breaks text matchers).
`list_missing_widget_keys` flags gaps.

**Generate the first test with `scaffold_patrol_test`** — emits a
`patrol_test/<name>_test.dart` smoke test that's **compile-verified against
patrol 4.7.x** (`flutter analyze`-clean out of the box), widget-Key based,
tagged `smoke`, and runs unchanged on **mobile and web**. It doesn't touch
your pubspec/build files — it returns the wiring steps + the exact
`run_patrol_test` commands. Then swap the placeholder keys for your
screen's real ones.

**Android native harness**

- `android/app/build.gradle(.kts)` → `defaultConfig`:
  - `testInstrumentationRunner = "pl.leancode.patrol.PatrolJUnitRunner"`
  - `testInstrumentationRunnerArguments["clearPackageData"] = "true"`
  - `testOptions.execution = "ANDROIDX_TEST_ORCHESTRATOR"`
  - `androidTestUtil("androidx.test:orchestrator:1.5.1")`
- `android/app/src/androidTest/java/<applicationId-path>/MainActivityTest.java`
  — the `@RunWith(PatrolJUnitRunner)` parameterized harness. **Package must
  equal `applicationId`.**

**iOS native harness**

- A **UI Testing Bundle** target `RunnerUITests` (tested target = `Runner`),
  deployment target 13+.
- `ios/RunnerUITests/RunnerUITests.m`:
  `@import patrol; PATROL_INTEGRATION_TEST_IOS_RUNNER(RunnerUITests)`
- Wire the pod: a `RunnerUITests` target in `ios/Podfile` inheriting the
  Runner pods (links the `patrol` pod), then `pod install`. (SPM works on
  patrol ≥ 4.7.0.)

**.gitignore** — add `integration_test/test_bundle.dart` (Patrol regenerates
it each run).

**Run it**

```bash
patrol test -t patrol_test/app_test.dart -d <deviceId>   # or the whole dir
```

…or via phone-controll: `run_patrol_test` / `run_patrol_suite` with
`platform="mobile"`, `serial=<udid>`. Tag a fast subset `smoke` for CI.

---

## 2. Per-app checklist — WEB (Patrol drives Chromium via Playwright)

The **same `patrol_test/*_test.dart` files** run on web. Branch
platform-specific behavior on `$.platform` (see §4). No app-side bootstrap.

- **Only manual prereq: Node.js** on the machine/CI runner. First
  `patrol test -d chrome` auto-installs Patrol's Node deps incl. Playwright
  + Chromium — budget download time + network on the first run.
- Web is **Chromium-only** (no Firefox/WebKit). `flavor` / `serial` /
  `build_mode` are ignored on web.
- Web element targeting uses `WebSelector` (CSS/XPath or a test-id) rather
  than mobile selectors — **verify the exact class name against your
  resolved patrol version (§4).**

**Run it**

```bash
patrol test -t patrol_test/app_test.dart -d chrome
```

…or via phone-controll `run_patrol_test`/`run_patrol_suite` with
`platform="web"` (forces `--device chrome`, requests a machine-readable
**Playwright JSON** report, and parses it for exact per-test counts). Add
`ci=true` for the headless-CI profile.

Complement e2e with the static/runtime web tools already in phone-controll:
`audit_web_app` (index.html / manifest / headers), `run_lighthouse` +
`ingest_lighthouse_report` (vitals), `ingest_har` (network cost),
`ingest_frame_timeline` (jank).

---

## 3. CI — get results onto a PR

- **JUnit for PR status (new in this release):** pass `junit_path` to
  `run_patrol_test` / `run_patrol_suite`. It writes JUnit XML (one
  `<testcase>` per test) for **web and mobile**, consumable by GitHub
  Actions / GitLab / Bitbucket Pipelines / Jenkins. A failing run always
  emits **red** XML — even a mobile run whose per-test output can't be
  scraped is reported as a failing synthetic case (never a silent green).
- **Headless-CI mode:** `ci=true` →
  - web: `--web-headless true`, `--web-retries 2`, a 30-min global timeout,
    `--web-video retain-on-failure`, and
    `--no-sandbox --disable-gpu --disable-dev-shm-usage` (needed in most
    containers).
  - native: `--full-isolation` + `--clear-permissions` (hermetic per test).
- **Cache** the Node + Playwright/Chromium artifacts across runs (first-run
  download is slow and networked).
- **Gate** the pipeline on `patrol doctor`, and treat `patrol` + `patrol_cli`
  as a matched pair (§0).
- Mobile CI runs against a booted emulator/simulator or a device farm —
  there is **no** `--web-headless` for mobile; use `patrol build
  android|ios` for device-farm binaries.

---

## 4. What changed 3.x → 4.x (and a correction)

- **Default test dir**: `integration_test/` → **`patrol_test/`** (4.0.0).
- **Dart/Flutter floor**: Dart ≥ 3.8, Flutter ≥ 3.32.
- **Native-automation API changed.** Older code used `$.native.tap(...)`.
  The 4.x cross-platform surface centers on **`$.platform`** with
  `MobileSelector(android:, ios:)` and `WebSelector(...)`.
  - ⚠️ **Correction to an earlier note of mine:** I previously wrote the
    migration target as `$.platform.action.maybe(web:, ios:, android:)`.
    That combinator does not exist — disregard it. **Verify the real
    surface against the `patrol` version your pubspec resolves** (its
    README / migration guide), then template it.

**How to verify before templating across the factory** (5 minutes, once):

```bash
# in one app that already resolved patrol 4.7.x:
patrol test -t patrol_test/app_test.dart -d chrome --dry-run 2>/dev/null || true
flutter analyze patrol_test/    # must be clean with your selector calls
```

Lock the confirmed snippet into the factory template only after
`flutter analyze` is clean on a real resolved patrol 4.7.x.

---

## 5. Physical iPhone runbook (one-time, for iOS UI driving)

iOS UI input (`tap`/`swipe`/`press_key`) routes through **WebDriverAgent
over usbmux** — it only works once the WDA runner is actually running on
the device. Order matters:

1. **Connect + trust.** USB, unlock, tap *Trust This Computer*. Keep the
   device **unlocked** for the whole session.
2. **Developer Mode ON.** Settings → Privacy & Security → Developer Mode →
   On (accept the reboot). If it won't turn on:
   `pymobiledevice3 amfi enable-developer-mode --udid <UDID>`.
3. **Mount a version-matched Developer Disk Image.**
   `pymobiledevice3 mounter auto-mount --udid <UDID>`.
   ⚠️ **CRITICAL:** an **iOS-26 device with a stale iOS-17 DDI** mounted
   breaks developer services *silently* — screenshots, syslog, and the
   XCTest session fail with no clear error. Unmount any stale 17.x image
   and re-auto-mount with Xcode 26.6's images so the DDI matches the
   device's iOS.
4. **(Only if you need pmd3 developer-tier services** — dvt screenshot /
   syslog — **not for the WDA launch itself)** start the tunnel in its own
   terminal, kept open all session:
   ```bash
   sudo $(which pymobiledevice3) remote tunneld
   ```
   (`sudo` resets `PATH`; `$(which …)` resolves the venv binary first.)
   ⚠️ **Tunnel-ownership conflict:** the WDA launch uses Xcode 26.6's
   CoreDevice tunnel, and there is only **one RSD tunnel per device**. If
   the runner won't start, **stop tunneld** and let Xcode own the tunnel.
5. **Get the UDID:** `pymobiledevice3 usbmux list` (or `xcrun xctrace list
   devices`).
6. **Build + sign WDA once:** `setup_webdriveragent udid=<UDID>
   team_id=<APPLE_TEAM_ID>` (or set `MCP_WDA_TEAM_ID`). On the device's
   first launch, trust the developer cert: Settings → General → VPN &
   Device Management. **Free personal-team profiles expire after 7 days** —
   re-run `setup_webdriveragent` when WDA stops launching.
7. **Launch the runner:** `start_wda_on_device udid=<UDID>` *(new in this
   release)*. It spawns `xcodebuild test-without-building` against the
   device (detached) and polls WDA `/status` over usbmux until ready
   (default 90 s).
8. **Verify:** `tap` / `swipe` / `press_key` / `type_text` now route
   through WDA automatically. Teardown when done:
   `pkill -f "test-without-building.*<UDID>"`.

If a `tap` returns `next_action="start_wda_on_device"`, the runner isn't
up — run step 7. If it returns `provide_team_id` / `check_xcode_signing`,
revisit steps 6/2/3.
