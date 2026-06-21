# Navigating fast: drive structurally, verify visually

> How to make an agent move through an app quickly when the work **isn't**
> visual verification. The slow default — *screenshot → reason over pixels
> → compute x,y → tap → screenshot again to confirm* — should be the
> **fallback**, not the loop you live in.

## The cost you're paying

One vision step costs, roughly:

| | cost |
|---|---|
| device screencap | ~100–400 ms |
| PNG encode + transfer | tens of ms |
| **image tokens** (a phone screenshot) | ~1,000–2,000 tokens |
| model localizes the element in pixels | ~1–3 s |
| x,y math | brittle to density / rotation / safe-area |

A structured **find-by-selector** costs an on-device query (tens of ms) and
a tiny text response. **≈10× faster, ≈10–50× cheaper per step, and
deterministic** — so no retry spiral when the tap lands a few pixels off.

## The one rule

**Reserve pixels for "does it *look* right." Everything else — getting
somewhere, tapping a known control, confirming a screen rendered — runs on
the structured layer.**

## The loop, replaced step by step

Every step of the screenshot loop has a no-vision replacement that ships
today:

| Vision-loop step | Structured replacement | Notes |
|---|---|---|
| screenshot + VLM to find an element | **`extract_ui_graph`** | Returns compact JSON: `clickables` / `inputs` / `texts`, each with `bounds`, `role`, `resource_id`, `text`. No image. |
| compute x,y, then `tap(x,y)` | **`tap(resource_id=… \| text=… \| class_name=…)`** | Resolves + taps **server-side in one call**. No coordinates. Get the selector from `extract_ui_graph`. |
| screenshot-poll to confirm | **`wait_for_element` / `assert_visible`** | Polls the hierarchy, not images. |
| tap then screenshot to verify | **`tap_and_verify`** | Action + "expect element appears" in one structured call. |
| tap through N screens to reach a state | **`test_deep_link`** | `myapp://orders/123` jumps straight there. Biggest win for "get to state X to do work." |
| re-derive a known flow every run | **`promote_sequence` + `replay_skill`** | Record once, replay deterministically — zero re-reasoning. |
| (Flutter) find a widget | **`find_flutter_widget` / `dump_widget_tree`** (VM Service / DWDS) + Patrol Keys | Semantic widget tree, not pixels; Key taps are locale-independent. |
| (Flutter) reach a state directly | **`call_service_extension` / `vm_evaluate`** | Navigate the router / set state programmatically — skips the UI walk entirely. |

### The canonical fast loop

```
extract_ui_graph              # one structured read of the screen
→ pick the element by resource_id / text
→ tap(resource_id="…")        # resolve + tap, no screenshot, no x,y
→ wait_for_element(text="…")  # confirm the transition, on the hierarchy
```

`take_screenshot` enters this loop only when the task is *literally* "verify
the UI looks correct" (a golden compare, a visual regression, a layout
check) — `compare_screenshot` / `save_golden_image` for that.

## `tap` by selector (v0.13.0)

`tap` now accepts a selector and resolves it server-side:

```jsonc
// fast path — no screenshot, no coordinate math:
tap {"resource_id": "com.example:id/btn_signin"}
tap {"text": "Sign in"}            // routes through the hardened text matcher
tap {"class_name": "android.widget.Button"}

// fallback — only for targets no selector can address:
tap {"bounds": "[480,1160][600,1240]"}   // tap the centre of a bounds rect from dump_ui
tap {"x": 540, "y": 1200}
```

`bounds` (v0.14.0) is the path for an element with **no** stable
selector — e.g. a Compose photo cell with empty `content-desc`: read its
rect from `dump_ui`/`extract_ui_graph` and tap the centre without doing
the maths yourself. (Note: some Compose surfaces ignore *all* injected
coordinate taps regardless of source — that's a platform accessibility
quirk, not a coordinate error.)

If a selector matches nothing it fails with `next_action:
capture_diagnostics` — it never taps a guessed coordinate. `text` reuses the
same NFC / NBSP / dump-scan matcher as `tap_text` (so Polish diacritics and
Samsung One UI work), and on Samsung the tap still falls back to
`adb shell input tap`.

## Optional: cache the hierarchy on a stable screen (v0.13.0)

Set **`MCP_UI_CACHE_TTL_MS`** (e.g. `750`) to cache the read-only UI dump for
that many milliseconds, so repeated `extract_ui_graph` / `dump_ui` on the
same screen don't re-hit the device. **Off by default.**

Safety: only the *observation* (`dump_ui`) is cached. Every action
(`tap` / `swipe` / `type_text` / `press_key`) clears the cache, and
`find` / `tap_text` always resolve against the **live** device — so the
cache can never decide where a tap lands. The worst case is an
observation that's at most `ttl_ms` stale, never across an action you just
took. Enable it for navigation work; leave it off when you need
guaranteed-fresh reads (e.g. waiting on async-loaded content).

## Collapse round-trips (v0.15.0)

Per-step latency is only half the story. The other half is **how many
times the model has to wake up**: total time ≈ round-trips × (model
reasoning + tool exec + transport). A 12-step flow is 12 model turns.
Collapse them:

- **`batch([{tool, args}, …])`** — run a known flow server-side in ONE
  round-trip. Each step still gets the full pipeline (image-cap / trace /
  truncate); `stop_on_error` halts at the first failure and returns a
  per-step trace. The model reasons once, not per step.
  ```jsonc
  batch {"steps": [
    {"tool": "tap", "args": {"resource_id": "btn_signin"}},
    {"tool": "wait_until", "args": {"text": "Loading", "gone": true}},
    {"tool": "assert_visible", "args": {"text": "Welcome"}}
  ]}
  ```
  For a *reusable, asserted* flow prefer **`run_test_plan`** (declarative
  YAML); use `batch` for ad-hoc sequences.
- **`wait_until(gone=true)`** — block until a spinner/dialog disappears
  (or `gone=false` until something appears) in one call, instead of a
  poll-loop where every check is a round-trip.
- **Diagnostics-on-failure** — when a `batch` step or `tap_and_verify`
  fails, a capped screenshot + recent error logs are folded into the
  result, so you don't spend another round-trip capturing them.
- **`restart_debug_session(full_restart=false)`** — hot reload to iterate
  code without the rebuild+reinstall round-trip.

## When you *do* need vision

- Visual regression / golden checks — `compare_screenshot`,
  `save_golden_image`, `update_goldens`.
- A control with no stable id/text/semantics (custom-drawn canvas, a game
  surface) — `tap(x, y)`, ideally after `ocr_screenshot` to locate it.
- Verifying *appearance* (colors, spacing, overflow) — that's the one job
  pixels are actually for.

Before sending a screenshot to the model, `inspect_image_safety` tells you
whether it's within the API's pixel cap, and `estimate_tokens` sizes any
large payload against your context budget.

## TL;DR for agents

1. `extract_ui_graph` to see the screen as data.
2. `tap(resource_id=… / text=…)` to act — never compute x,y if a selector exists.
3. `wait_for_element` / `tap_and_verify` to confirm — not a screenshot.
4. `test_deep_link` to jump to a screen; `replay_skill` to repeat a known flow.
5. Screenshot only to verify how something **looks**.
