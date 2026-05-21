# Designing test scenarios for real-device mobile testing

A research-grounded framework for the question every QA-aware
team asks: **"what should we actually test before we ship?"**

This doc codifies the taxonomy the [`propose_test_scenarios`](
../packages/phone-controll/src/mcp_phone_controll/domain/usecases/propose_test_scenarios.py)
tool returns programmatically. Read it as a checklist; run the
tool when you want the project-aware version with detected
features (camera permission, deep links, IAP, etc.).

## The 12 categories of real-world mobile failure

| Category | What it covers | Why it bites in production |
|---|---|---|
| **Happy path** | The canonical user journeys | If this breaks, the app is broken |
| **Permission** | What happens when users say "no" | Half of crash reports trace here |
| **Network** | Offline, slow, drops mid-action | Users live on imperfect connections |
| **Input** | Empty, long, emoji, RTL, paste | Real users paste 🎉 into your "name" field |
| **Interruption** | Call, alarm, notification mid-flow | The 30-second-flow assumption is wrong |
| **Lifecycle** | Cold start, OS kill, deep link, logout | "Reopened from background" is the most-traveled path |
| **Accessibility** | Screen reader, font scale, tap targets | EU EAA 2025 makes this regulatory |
| **Localization** | RTL, long translations, locale switch | German strings are 30-40% longer than English |
| **Device matrix** | Low-end, tablet, foldable | Emerging-market users are on 2 GB devices |
| **Performance** | Frame jank, memory growth, app-size | The #1 user-perceived quality signal |
| **Security** | Secrets, tokens, biometrics, IAP restore | App Store auto-rejects on many of these |
| **Data** | Empty / malformed / large server responses | Real backends do all of these |

## The "ship-or-don't" priority tiers

| Tier | Meaning | When you skip |
|---|---|---|
| **P0** | Must-test before any ship. Bugs here block users from completing core flows OR introduce privacy/security regressions. | Never. |
| **P1** | Should-test for a credible release. Bugs here annoy users but don't block. | Internal beta only. |
| **P2** | Nice-to-test — polish + edge cases. | Pre-1.0 / non-public builds. |

The tool returns scenarios sorted by tier so you can answer
"what's the smallest subset that's defensible to ship?" instantly:
the P0 set.

## How this taxonomy was built

Distilled from:

| Source | What it contributes |
|---|---|
| [**Google Android Quality Guidelines (CAQ)**](https://developer.android.com/quality) | Permission denial, cold start, low-end devices, offline behavior |
| [**Apple HIG + App Store Review §2-§5**](https://developer.apple.com/design/human-interface-guidelines/testing) | State restoration, IAP restore, biometric fallbacks |
| **ISO/IEC 25010:2011 — Software Quality Model** | The 8-category quality framework that maps onto these 12 |
| [**WCAG 2.2 Level AA**](https://www.w3.org/WAI/standards-guidelines/wcag/) | Accessibility: tap targets, text resize, contrast, screen-reader |
| **EU Accessibility Act (EAA) 2025** | Regulatory deadline that promotes WCAG from "nice to have" to "law" in many EU markets |
| [**OWASP Mobile Top 10**](https://owasp.org/www-project-mobile-top-10/) | Insecure storage, improper validation, insecure configuration |
| **PSD2 / EMV 3DS** | 3DS challenges mid-payment (mandatory in EU) |
| **Drizz 2026 mobile-QA industry survey** | Cost of selector-maintenance + most-painful real-world failure modes |
| [**ICU CLDR**](https://cldr.unicode.org/) | Localization length variance, RTL behaviors, grapheme cluster handling |
| **Flutter team performance docs** | 60/120 fps budgets, build/raster phase guidance |
| **LeanCode Patrol patterns** | Recommended flows for state preservation + interruption testing |
| [**OAuth 2.0 RFC 6749**](https://datatracker.ietf.org/doc/html/rfc6749) | Token refresh, redirect-after-deep-link, error states |

None of these on their own is a complete test plan. The taxonomy
is what emerges when you intersect them.

## The 25 canonical scenarios

These apply regardless of what your app does. They're the
P0/P1/P2 prioritized starting set.

### Happy path (P0)

1. **Cold launch → main screen renders within 3s.**
   Google Android Vitals flags > 5s cold-start times. 3s is the
   user-perceptible threshold for "slow." Boot from fully
   terminated state and measure time-to-first-frame.

2. **Primary user journey end-to-end.**
   The single most-traveled path through the app — the journey
   the PM would describe in one sentence. If this fails, the app
   is broken.

### Permission (P0)

3. **Deny every runtime permission, app still launches.**
   Tap "Deny" on every permission dialog on first launch. The
   app must not crash and must surface a path forward (settings
   deep link, retry button, or graceful degradation).
   *Standard: Google CAQ — Permission Handling*

4. **Grant permission, then revoke from OS settings while app runs.**
   App must detect the change and re-prompt (or fail gracefully)
   instead of silently calling into the platform with no
   permission.

### Network (P0)

5. **Cold start with no network.**
   Boot the app with airplane mode on. If it relies on backend
   for first paint, it must show a clear offline state — not a
   white screen or thrown exception.

6. **Network drops mid-action.**
   User starts an action that hits the network. Mid-request,
   network drops. App must show a retry/offline state with the
   user's input preserved.
   *Drizz 2026 survey: top-5 user-visible bug class.*

7. **Slow network (2G simulation).**
   Throttle to 2G speeds. UI must show progress indicators for
   any operation > 1 second. Frequent omission — users on
   spotty connections think the app froze.

### Input (P1)

8. **Submit form with empty required fields.**
   Inline validation must trigger before the network call.

9. **Paste emoji + RTL + special chars into text fields.**
   Real users paste 🎉, Arabic/Hebrew text, smart quotes
   (' '), and combined characters. Field must not crash or
   truncate mid-grapheme cluster.
   *Standard: Unicode TR29.*

10. **Maximum-length input (server limit).**
    Paste the server's max-length string +1 char. Client should
    either clip with feedback or reject before sending — never
    send and let the server 400.

### Interruption (P0/P1)

11. **Incoming phone call during a multi-step flow.**
    After dismissing, the app must restore the exact step + user
    input intact.

12. **App backgrounded mid-flow, OS kills it, user re-opens.**
    Backgrounded apps can be killed at any moment under memory
    pressure. Recents-tap restore should land users where they
    left off — not at the splash screen.

### Lifecycle (P0)

13. **Logout → login → all stale data cleared.**
    After logout, no previous user's data should be visible.
    Caches leaking across users is a P0 privacy bug.

### Accessibility (P1)

14. **TalkBack/VoiceOver can navigate the main flow.**
    EU EAA 2025 makes this regulatory in many countries.

15. **Tap targets ≥ 48×48 dp.**
    WCAG 2.2 SC 2.5.5 (Target Size). Tiny tap targets are the #1
    cause of store-review accessibility complaints.

16. **200% text scale doesn't break layouts.**
    Android Display size / iOS Dynamic Type cranked to max.
    RenderFlex overflows are the most common bug class here.

### Localization (P1)

17. **Switch device locale to RTL (Arabic/Hebrew).**
    Layout direction should flip; directional icons should mirror.

18. **Long-translation strings don't truncate or overflow.**
    German strings can be 30-40% longer than English. Buttons +
    tabs + dialog titles need to handle this without
    ellipsis-cutting key meaning.

### Device matrix (P1/P2)

19. **Low-end device: 2GB RAM, slow CPU.**
    Major share of emerging markets. Memory + frame budgets are
    stricter here.

20. **Tablet / large-screen layout.**
    Master-detail layouts, multi-column lists, and rotation
    should adapt — not just scale up.

### Performance (P1)

21. **Scroll a long list — frame rate stays ≥ 60fps.**
    The single most common jank source. Static analysis doesn't
    catch it; the MCP's `start_frame_profile` / `stop_frame_profile`
    do.

22. **Memory doesn't grow across 10× navigation cycles.**
    Push and pop the same route 10 times. Heap should return to
    baseline. Growth = uncleaned subscriptions/controllers.
    Use the MCP's `allocation_profile(reset_accumulator=True)` +
    `detect_undisposed_controllers`.

### Security (P0)

23. **No secrets / API keys in the built app.**
    Decompile (or grep) the release APK/IPA for "apiKey",
    "secret", "password". Common bug: dev-only debugging
    constants shipped to production.
    *Standard: OWASP Mobile Top 10 — Insecure Configuration.*

### Data (P1)

24. **App handles a malformed / empty backend response.**
    Mock the backend to return `{}` or `null` for a list
    endpoint. App should show empty-state UI — not crash or
    infinite-load.

### Performance — app size (P1)

25. **Release-build app size hasn't grown by > 500 KB without justification.**
    Use the MCP's `analyze_app_size(baseline_json_path=…)`.
    Catches the "we just added a 15MB ML model" regression at
    PR time.

## Project-specific additions

Beyond the canonical 25, the tool adds **conditional scenarios**
based on what your app actually does. Detected by inspecting
`AndroidManifest.xml`, `Info.plist`, `pubspec.yaml`, and routing
config. Examples:

| If your app uses… | Added scenarios |
|---|---|
| Camera (`NSCameraUsageDescription`, `CAMERA`, `image_picker`) | Deny-camera fallback to gallery |
| Location (`ACCESS_FINE_LOCATION`, `geolocator`) | OS location disabled, not just permission denied |
| Notifications (Android 13+ runtime, `flutter_local_notifications`) | Notifications denied, app still works |
| Deep links (intent filters, `GoRouter`) | Cold-start deep link, auth-gated deep link |
| In-app purchase (`in_app_purchase`) | Sandbox purchase success, restore purchases |
| Biometrics (`local_auth`, FaceID) | Hardware unavailable / not enrolled fallback |
| Login (`firebase_auth`, `google_sign_in`, OAuth) | Wrong password rate-limit, token refresh |
| AR / ML Kit (`ar_*`, `google_mlkit`) | Unsupported-device detection |
| Payments (`stripe`, `google_pay`) | 3DS / SCA mid-payment |
| Localization (`flutter_localizations`) | Missing translation keys per locale |
| Dark mode (`ThemeMode`) | OS-toggle mid-session |

These don't replace the canonical 25 — they extend it. A typical
production-ready app ends up with ~30-50 scenarios after
enrichment.

## How to actually use this

The fastest workflow:

```python
# 1. Generate the checklist
result = propose_test_scenarios(
  project_path="/Users/me/Desktop/myapp",
  focus_areas=["happy_path", "permission", "network"],  # P0 categories
  top_n=15,
)

# 2. Read result.advice for the headline number
# "Proposed 15 scenarios (10 P0 / 5 P1). 3 project-specific
# based on detected features: camera, location, deep_links."

# 3. For each scenario, run the tool sequence
for scenario in result.scenarios:
    print(f"=== {scenario.name} ({scenario.priority.value}) ===")
    print(scenario.description)
    print(f"Standard: {scenario.standard}")
    print(f"Run: {' → '.join(scenario.tool_sequence)}")
```

The agent can iterate through this and turn each entry into a
YAML test-plan phase or a Patrol `testWidgets()` block.

## When NOT to use this

- **You already have a defined test plan.** This tool generates
  ideas; if you've already converged, don't re-litigate.
- **You're prototyping.** Test scenarios are for things you ship.
  At the prototype stage, just dogfood.
- **You're testing a single isolated widget.** Use Flutter's
  standard `testWidgets()` patterns + `run_widget_test`. The
  scenario taxonomy is for app-level behavior.

## See also

- [`docs/operational-gotchas.md`](operational-gotchas.md) — pre-flight
  issues that cost an hour the first time
- [`docs/tools-by-category.md`](tools-by-category.md) — full tool
  catalog grouped by user goal
- [`examples/scenarios/`](../examples/scenarios/) — end-to-end
  worked examples
- [`docs/runbook.md`](runbook.md) — top-10 production failure modes
